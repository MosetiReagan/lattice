import pytest

from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.types import GenerationRequest, LatticeError


async def test_incompatible_draft_has_explicit_fallback(settings):
    settings.draft_model_id = "not-registered"
    backend = LlamaCppBackend(settings, settings.models[0])
    request = GenerationRequest(
        model="test-model", prompt="x", optimization={"mode": "speculative"}
    )
    reason = await backend.configure(request)
    assert reason and backend.identity["strategy"] == "standard"
    request.optimization.allow_fallback = False
    with pytest.raises(LatticeError) as error:
        await backend.configure(request)
    assert error.value.code == "incompatible_strategy"


async def test_memory_budget_cannot_raise_operator_cap(settings):
    backend = LlamaCppBackend(settings, settings.models[0])
    await backend.configure(
        GenerationRequest(model="test-model", prompt="x", max_memory_mb=16384)
    )
    assert backend._memory_cap == settings.worker_address_space_mb
