"""Small baseline API; unsupported optimization controls fail explicitly."""

import asyncio
import hmac
import json
import time
import uuid
from collections import deque
from contextlib import aclosing, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from lattice.config import select_model
from lattice.observability.measure import summarize

from .config import Settings, public_model
from .runtime import Runtime
from .types import GenerationRequest, LatticeError


def error_response(exc: LatticeError) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": str(exc), "code": exc.code}}, status_code=exc.status
    )


async def while_connected(operation, request: Request):
    """Cancel queued/non-streamed work when the client leaves, before response headers."""

    async def disconnected():
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return

    task = asyncio.ensure_future(operation)
    monitor = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait(
            {task, monitor}, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            return await task
        raise LatticeError("Client disconnected", 499, "client_disconnected")
    finally:
        for pending in (task, monitor):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, monitor, return_exceptions=True)


class RequestLimits:
    """ASGI body bound enforced during receipt, including chunked requests."""

    def __init__(self, app, api_key: str | None, rate: int):
        self.app, self.api_key, self.rate = app, api_key, rate
        self.arrivals = deque()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["path"] not in ("/health", "/metrics"):
            expected = ("Bearer " + self.api_key).encode() if self.api_key else None
            if expected and not hmac.compare_digest(
                headers.get(b"authorization", b""), expected
            ):
                return await error_response(
                    LatticeError("Invalid API credential", 401, "unauthorized")
                )(scope, receive, send)
            now = time.monotonic()
            while self.arrivals and self.arrivals[0] <= now - 60:
                self.arrivals.popleft()
            if len(self.arrivals) >= self.rate:
                return await error_response(
                    LatticeError("Rate limit exceeded", 429, "rate_limited")
                )(scope, receive, send)
            self.arrivals.append(now)
        try:
            if int(headers.get(b"content-length", b"0")) > 65536:
                raise LatticeError(
                    "Request body exceeds 65536 bytes", 413, "body_too_large"
                )
        except ValueError:
            return await error_response(LatticeError("Invalid content length"))(
                scope, receive, send
            )
        except LatticeError as exc:
            return await error_response(exc)(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 65536:
                        return await error_response(
                            LatticeError(
                                "Request body exceeds 65536 bytes",
                                413,
                                "body_too_large",
                            )
                        )(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await error_response(
                LatticeError("Request body receive timeout", 408, "body_timeout")
            )(scope, receive, send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class BenchmarkJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str
    trials: int = Field(default=3, ge=1, le=5)


def create_app(
    settings: Settings,
    runtime: Runtime,
    api_key: str | None = None,
    preload: bool = True,
) -> FastAPI:
    jobs = {}
    job_tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        try:
            if preload:
                await runtime.backend.start()
            yield
        finally:
            for task in list(job_tasks):
                task.cancel()
            if job_tasks:
                await asyncio.gather(*job_tasks, return_exceptions=True)
            close = getattr(runtime.backend, "aclose", None)
            if close:
                await close()
            else:
                runtime.backend.stop()

    app = FastAPI(title="Lattice baseline", version="0.3.0.dev0", lifespan=lifespan)
    app.add_middleware(
        RequestLimits, api_key=api_key, rate=settings.requests_per_minute
    )

    @app.exception_handler(LatticeError)
    async def lattice_error(request, exc):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "details": [
                        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                        for e in exc.errors()
                    ],
                }
            },
            status_code=422,
        )

    @app.get("/health")
    async def health():
        # No host inventory, paths, secrets or private cache data.
        return {"status": "ok", "stage": "baseline", "backend": "llama.cpp"}

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                public_model(m)
                for m in settings.models
                if runtime.backend_factory is not None or m.id == runtime.model_id
            ],
        }

    @app.get("/v1/optimization/status")
    async def optimization_status():
        return {
            "default_strategy": "standard",
            "selected_strategy": runtime.backend.identity.get("strategy", "standard"),
            "adaptive": bool(settings.policy_file) and settings.native_slots == 1,
            "speculative": bool(settings.draft_model_id) and settings.native_slots == 1,
            "prefix_reuse": settings.native_slots == 1,
            "native_slots": settings.native_slots,
            "concurrent_standard": settings.native_slots > 1,
            "native_stochastic_speculation": False,
            "note": "Greedy, evidence-scoped paths only. Default is standard; quality-unqualified variants are explicit-only.",
        }

    @app.get("/v1/metrics")
    async def metrics():
        return runtime.metrics()

    @app.get("/metrics")
    async def prometheus_metrics():
        from fastapi.responses import PlainTextResponse

        data = runtime.metrics()
        lines = [
            "# HELP lattice_requests_total Total requests submitted",
            "# TYPE lattice_requests_total counter",
            f"lattice_requests_total {data.get('requests_submitted', 0)}",
            "# HELP lattice_requests_completed Total requests completed",
            "# TYPE lattice_requests_completed counter",
            f"lattice_requests_completed {data.get('requests_completed', 0)}",
            "# HELP lattice_requests_preempted Total requests preempted by higher priority traffic",
            "# TYPE lattice_requests_preempted counter",
            f"lattice_requests_preempted {data.get('requests_preempted', 0)}",
            "# HELP lattice_requests_resumed Total preempted requests seamlessly resumed",
            "# TYPE lattice_requests_resumed counter",
            f"lattice_requests_resumed {data.get('requests_resumed', 0)}",
            "# HELP lattice_queue_depth Current requests waiting in admission queue",
            "# TYPE lattice_queue_depth gauge",
            f"lattice_queue_depth {data.get('queue_depth', 0)}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n")

    @app.post("/v1/benchmarks/run", status_code=202)
    async def benchmarks(body: BenchmarkJobRequest):
        if not api_key:
            raise LatticeError(
                "Configure operator API authentication before starting benchmark jobs",
                401,
                "operator_auth_required",
            )
        select_model(settings, body.model)
        if runtime.backend_factory is None and body.model != runtime.model_id:
            raise LatticeError(
                "Model is not served by this worker", 404, "model_not_served"
            )
        if job_tasks:
            raise LatticeError(
                "A profiling job is already running", 429, "benchmark_busy"
            )
        job_id = "bench-" + uuid.uuid4().hex
        if len(jobs) >= 16:
            jobs.pop(next(iter(jobs)))
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "scope": "Bounded live-serving profile, not isolated research benchmark",
            "model": body.model,
        }

        async def execute():
            jobs[job_id]["status"] = "running"
            rows = []
            try:
                for index in range(body.trials):
                    result = await runtime.generate(
                        GenerationRequest(
                            model=body.model,
                            prompt="The careful engineer records measurements before comparing results. The next step is",
                            max_tokens=16,
                            timeout_seconds=60.0,
                        )
                    )
                    rows.append(result["metadata"])
                jobs[job_id].update(
                    status="completed",
                    latency_ms=summarize([r["total_ms"] for r in rows]),
                    records=rows,
                    quality=None,
                )
            except asyncio.CancelledError:
                jobs[job_id]["status"] = "cancelled"
                raise
            except LatticeError as exc:
                jobs[job_id].update(status="failed", error_code=exc.code)

        task = asyncio.create_task(execute())
        job_tasks.add(task)
        task.add_done_callback(job_tasks.discard)
        return dict(jobs[job_id])

    @app.get("/v1/benchmarks/jobs/{job_id}")
    async def benchmark_status(job_id: str):
        if job_id not in jobs:
            raise LatticeError("Unknown profiling job", 404, "job_not_found")
        return jobs[job_id]

    async def respond(body: GenerationRequest, chat: bool, request: Request):
        if chat and body.messages is None:
            raise LatticeError("Chat completions require messages")
        if not chat and body.prompt is None:
            raise LatticeError("Text generation requires prompt")
        if not body.stream:
            result = await while_connected(runtime.generate(body), request)
            if not chat:
                return result
            record = result["metadata"]
            return {
                "id": record["id"],
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": result["text"]},
                        "finish_reason": record["finish_reason"],
                    }
                ],
                "usage": usage(record),
                "lattice": record,
            }
        # Preflight tokenization/context/model/backpressure before sending HTTP 200.
        events = runtime.events(body)
        try:
            first = await while_connected(anext(events), request)
        except BaseException:
            await events.aclose()
            raise

        async def sse():
            try:
                async with aclosing(events):
                    request_id = first["id"]
                    if chat:
                        yield pack(
                            {
                                "id": request_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": body.model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"role": "assistant"},
                                        "finish_reason": None,
                                    }
                                ],
                                "lattice": first,
                            }
                        )
                    else:
                        yield pack(first)
                    async for event in events:
                        if chat:
                            if event["type"] == "token":
                                yield pack(
                                    {
                                        "id": request_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": body.model,
                                        "choices": [
                                            {
                                                "index": 0,
                                                "delta": {"content": event["text"]},
                                                "finish_reason": None,
                                            }
                                        ],
                                    }
                                )
                            elif event["type"] == "done":
                                yield pack(
                                    {
                                        "id": request_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": body.model,
                                        "choices": [
                                            {
                                                "index": 0,
                                                "delta": {},
                                                "finish_reason": event["record"][
                                                    "finish_reason"
                                                ],
                                            }
                                        ],
                                        "usage": usage(event["record"]),
                                        "lattice": event["record"],
                                    }
                                )
                        else:
                            yield pack(event)
                    yield "data: [DONE]\n\n"
            except LatticeError as exc:
                # Headers already sent: explicit error event, no successful DONE sentinel.
                yield pack({"error": {"message": str(exc), "code": exc.code}})

        return StreamingResponse(
            sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/generate")
    async def generate(body: GenerationRequest, request: Request):
        return await respond(body, False, request)

    @app.post("/v1/chat/completions")
    async def chat(body: GenerationRequest, request: Request):
        return await respond(body, True, request)

    return app


def pack(event: dict) -> str:
    return "data: " + json.dumps(event) + "\n\n"


def usage(record: dict) -> dict:
    return {
        "prompt_tokens": record["prompt_tokens"],
        "completion_tokens": record["completion_tokens"],
        "total_tokens": (record["prompt_tokens"] or 0) + record["completion_tokens"],
    }
