import json

import httpx
import pytest
from test_runtime import FakeBackend

from lattice.api import create_app
from lattice.runtime import Runtime


@pytest.fixture
def app(settings):
    return create_app(
        settings,
        Runtime(settings, "test-model", FakeBackend()),
        api_key="test-key",
        preload=False,
    )


async def test_auth_models_and_validation(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/health")).status_code == 200
        metrics_resp = await c.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "lattice_requests_total" in metrics_resp.text
        assert "lattice_queue_depth" in metrics_resp.text
        assert (await c.get("/v1/models")).status_code == 401
        c.headers["Authorization"] = "Bearer test-key"
        models = (await c.get("/v1/models")).json()
        assert models["data"][0]["id"] == "test-model"
        assert "/not/used" not in json.dumps(models)
        bad = await c.post(
            "/v1/generate",
            json={"model": "test-model", "prompt": "secret", "max_tokens": 9999},
        )
        assert bad.status_code == 422 and "secret" not in bad.text
        unknown = await c.post("/v1/generate", json={"model": "../bad", "prompt": "hi"})
        assert unknown.status_code == 404
        assert (await c.post("/v1/benchmarks/run")).status_code == 422


async def test_chat_stream_structure(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-key"},
    ) as c:
        response = await c.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )
        data = [
            line[6:] for line in response.text.splitlines() if line.startswith("data: ")
        ]
        assert data[-1] == "[DONE]"
        chunks = [json.loads(d) for d in data[:-1]]
        assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
        assert chunks[1]["choices"][0]["delta"]["content"] == "hello"
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        assert chunks[-1]["usage"]["completion_tokens"] == 1
        assert chunks[-1]["lattice"]["strategy"] == "standard"


async def test_chunked_body_limit(app):
    async def body():
        for _ in range(4):
            yield b"x" * 20000

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-key"},
    ) as c:
        response = await c.post("/v1/generate", content=body())
        assert response.status_code == 413


async def test_global_rate_limit(settings):
    settings.requests_per_minute = 1
    app = create_app(
        settings, Runtime(settings, "test-model", FakeBackend()), preload=False
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/v1/models")).status_code == 200
        assert (await c.get("/v1/models")).status_code == 429
        assert (await c.get("/health")).status_code == 200


async def test_bounded_benchmark_jobs(app):
    import asyncio

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-key"},
    ) as c:
        invalid = await c.post(
            "/v1/benchmarks/run", json={"model": "test-model", "trials": 1000}
        )
        assert invalid.status_code == 422
        response = await c.post(
            "/v1/benchmarks/run", json={"model": "test-model", "trials": 2}
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        for _ in range(20):
            result = (await c.get("/v1/benchmarks/jobs/" + job_id)).json()
            if result["status"] == "completed":
                break
            await asyncio.sleep(0)
        assert result["status"] == "completed" and result["latency_ms"]["n"] == 2
