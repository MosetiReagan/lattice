"""Real HTTP disconnect isolation through a two-slot gateway and native worker."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from lattice.config import load_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LATTICE_INTEGRATION") != "1",
        reason="Real CPU integration is opt-in",
    ),
]


async def test_http_cancel_keeps_peer_and_shared_worker_alive(tmp_path):
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "configs/local.json")
    settings.log_directory = str(tmp_path)
    settings.requests_per_minute = 1000
    config = tmp_path / "config.json"
    config.write_text(settings.model_dump_json())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "gateway.log").open("w") as logs:
        server = subprocess.Popen(  # noqa: ASYNC220 - bounded native process launch without preexec_fn
            [
                sys.executable,
                "-m",
                "lattice.cli",
                "--config",
                str(config),
                "serve",
                "--model",
                settings.models[0].id,
                "--native-slots",
                "2",
                "--port",
                str(port),
            ],
            stdout=logs,
            stderr=logs,
            env=dict(os.environ, LATTICE_API_KEY="test-concurrent-key"),
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                trust_env=False,
                timeout=30,
                headers={"Authorization": "Bearer test-concurrent-key"},
            ) as client:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    assert server.poll() is None, (tmp_path / "gateway.log").read_text()
                    try:
                        if (await client.get("/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Concurrent gateway startup timeout")
                children = (
                    Path(f"/proc/{server.pid}/task/{server.pid}/children")
                    .read_text()
                    .split()
                )
                assert children
                started = asyncio.Event()
                body = {
                    "model": settings.models[0].id,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Write a long numbered list of 500 cities.",
                        }
                    ],
                    "max_tokens": 128,
                    "stream": True,
                }

                async def peer():
                    chunks = []
                    async with client.stream(
                        "POST", "/v1/chat/completions", json=body
                    ) as response:
                        assert response.status_code == 200
                        async for line in response.aiter_lines():
                            if line.startswith("data: ") and line[6:] != "[DONE]":
                                item = json.loads(line[6:])
                                chunks.append(item)
                                if item["choices"][0]["delta"].get("content"):
                                    started.set()
                    return chunks

                task = asyncio.create_task(peer())
                try:
                    await asyncio.wait_for(started.wait(), 10)
                    other = {**body, "max_tokens": 512}
                    async with client.stream(
                        "POST", "/v1/chat/completions", json=other
                    ) as response:
                        assert response.status_code == 200
                        async for line in response.aiter_lines():
                            if line.startswith("data: ") and line[6:] != "[DONE]":
                                item = json.loads(line[6:])
                                if item["choices"][0]["delta"].get("content"):
                                    break
                    for _ in range(100):
                        metrics = (await client.get("/v1/metrics")).json()
                        if metrics["backend_slots"]["verified_cancellations"] >= 1:
                            break
                        await asyncio.sleep(0.02)
                    else:
                        pytest.fail("Native per-request cancellation was not confirmed")
                    chunks = await task
                    assert chunks[-1]["choices"][0]["finish_reason"] in (
                        "length",
                        "stop",
                    )
                    assert chunks[-1]["lattice"]["status"] == "completed"
                    assert chunks[-1]["lattice"]["native_slots"] == 2
                    assert (
                        Path(f"/proc/{server.pid}/task/{server.pid}/children")
                        .read_text()
                        .split()
                        == children
                    )
                    assert metrics["backend_slots"]["unconfirmed_cleanup"] == 0
                    status = (await client.get("/v1/optimization/status")).json()
                    assert status["concurrent_standard"] and not status["adaptive"]
                    assert (await client.get("/slots")).status_code == 404
                    assert (
                        await client.delete("/v1/stream?conv_id=anything")
                    ).status_code == 404
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
