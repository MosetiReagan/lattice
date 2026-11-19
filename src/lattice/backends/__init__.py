"""Backend boundary; no controller or routing implementation is coupled here."""

from collections.abc import AsyncIterator
from typing import Protocol

from lattice.types import GenerationRequest


class Backend(Protocol):
    identity: dict

    async def start(self) -> None: ...
    def stop(self) -> None: ...
    async def events(self, request: GenerationRequest) -> AsyncIterator[dict]: ...
