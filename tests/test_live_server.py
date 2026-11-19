"""Actual loopback HTTP and SSE with the real CPU worker."""

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
        reason="Real model integration is opt-in",
    ),
]


async def test_real_http_stream_disconnect_and_recovery(tmp_path):
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "configs/local.json")
    settings.log_directory = str(tmp_path)
    settings.models.append(
        settings.models[0].model_copy(
            update={"id": "broken-variant", "sha256": "0" * 64}
        )
    )
    config = tmp_path / "config.json"
    config.write_text(settings.model_dump_json())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    model = settings.models[0].id
    env = dict(os.environ, LATTICE_API_KEY="integration-only-key")
    with (tmp_path / "server.log").open("w") as logs:
        server = subprocess.Popen(  # noqa: ASYNC220 - only spawn; no preexec_fn
            [
                sys.executable,
                "-m",
                "lattice.cli",
                "--config",
                str(config),
                "serve",
                "--model",
                model,
                "--port",
                str(port),
            ],
            stdout=logs,
            stderr=logs,
            env=env,
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", timeout=30, trust_env=False
            ) as client:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    assert server.poll() is None, (tmp_path / "server.log").read_text()
                    try:
                        if (await client.get("/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("API server startup timeout")
                assert (await client.get("/v1/models")).status_code == 401
                client.headers["Authorization"] = "Bearer integration-only-key"
                body = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "What is 2 + 2? Answer briefly."}
                    ],
                    "max_tokens": 16,
                }
                reply = await client.post("/v1/chat/completions", json=body)
                assert reply.status_code == 200, reply.text
                assert reply.json()["choices"][0]["message"]["content"].strip()
                assert reply.json()["lattice"]["strategy"] == "standard"
                body["stream"] = True
                chunks = []
                async with client.stream(
                    "POST", "/v1/chat/completions", json=body
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            chunks.append(line[6:])
                assert chunks[-1] == "[DONE]"
                assert json.loads(chunks[-2])["choices"][0]["finish_reason"] in (
                    "stop",
                    "length",
                )
                # Abort only after an actual text chunk, not merely headers/role metadata.
                body["messages"][0]["content"] = (
                    "Write a long numbered list of 500 cities."
                )
                body["max_tokens"] = 512
                async with client.stream(
                    "POST", "/v1/chat/completions", json=body
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            item = json.loads(line[6:])
                            if item["choices"][0]["delta"].get("content"):
                                break
                for _ in range(100):
                    metrics = (await client.get("/v1/metrics")).json()
                    if (
                        metrics["counters"].get("cancelled", 0) >= 1
                        and not metrics["active_requests"]
                    ):
                        break
                    await asyncio.sleep(0.05)
                else:
                    pytest.fail("Disconnect failed to cancel active generation")
                body["stream"] = False
                body["max_tokens"] = 4
                reply = await client.post("/v1/chat/completions", json=body)
                assert reply.status_code == 200, reply.text
                assert reply.json()["usage"]["completion_tokens"] <= 4
                assert reply.json()["lattice"]["backend"]["device"] == "cpu"
                variants = [
                    m for m in settings.models if m.id == "qwen2.5-0.5b-instruct-q8_0"
                ]
                if variants:
                    body["model"] = variants[0].id
                    switched = await client.post("/v1/chat/completions", json=body)
                    assert switched.status_code == 200, switched.text
                    assert (
                        switched.json()["lattice"]["backend"]["model_sha256"]
                        == variants[0].sha256
                    )
                body["model"] = "broken-variant"
                broken = await client.post("/v1/chat/completions", json=body)
                assert (
                    broken.status_code == 503
                    and broken.json()["error"]["code"] == "artifact_mismatch"
                )
                body["model"] = model
                restored = await client.post("/v1/chat/completions", json=body)
                assert restored.status_code == 200, restored.text
                assert (
                    restored.json()["lattice"]["backend"]["model_sha256"]
                    == settings.models[0].sha256
                )

        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
