"""Backend boundary; no controller or routing implementation is coupled here."""

from collections.abc import AsyncIterator
from typing import Protocol

from lattice.types import GenerationRequest


class Backend(Protocol):
    identity: dict

    async def start(self) -> None: ...
    def stop(self) -> None: ...
    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]: ...


def create_backend(settings, model) -> Backend:
    """Construct the compatible serial or immutable multi-slot worker."""
    if settings.native_slots > 1:
        from .batched import BatchedLlamaBackend

        return BatchedLlamaBackend(settings, model)
    from .llama_cpp import LlamaCppBackend

    return LlamaCppBackend(settings, model)
