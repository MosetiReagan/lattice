"""Isolated eligibility/lease tests; no mock is GPU or performance evidence."""

from dataclasses import replace

from lattice.backends.batched import BatchedLlamaBackend, SlotLease
from lattice.cache.prefix import CacheIdentity
from lattice.types import GenerationRequest, Optimization


def make_backend(settings):
    settings.native_slots = 2
    settings.models[0].kv_bytes_per_token = 12288
    settings.cache_limit_mb = 64
    settings.cache_min_tokens = 1
    return BatchedLlamaBackend(settings, settings.models[0])


def test_explicit_operator_permission_and_full_pool_budget_are_required(settings):
    backend = make_backend(settings)
    assert backend.supported_modes() == {"standard"}
    settings.concurrent_prefix_cache = True
    assert backend.supported_modes() == {"standard", "cached"}
    settings.cache_limit_mb = 32
    assert backend.supported_modes() == {"standard"}


async def test_slot_state_and_standard_mode_never_share_eligibility(settings):
    backend = make_backend(settings)
    settings.concurrent_prefix_cache = True
    cached = GenerationRequest(
        model="test-model", prompt="same", optimization=Optimization(mode="cached")
    )
    private = GenerationRequest(model="test-model", prompt="same")
    one, two = SlotLease(0, "one"), SlotLease(1, "two")
    strategy, prefix = backend.execution_state(cached, one)
    identity = CacheIdentity("single-operator", "m", "t", "b", 2048, "f16", "rope")
    prefix.remember(identity, (1, 2, 3))
    assert strategy == "cached" and one.cache_enabled
    other_strategy, other = backend.execution_state(private, two)
    assert other_strategy == "standard" and not two.cache_enabled
    assert other is not prefix and not other.plan(identity, (1, 2, 3)).reuse
    assert prefix.plan(identity, (1, 2, 3)).reuse
    assert not prefix.plan(replace(identity, tenant="another"), (1, 2, 3)).reuse
    assert not prefix.tokens


def test_unapproved_payload_cannot_turn_cache_on(settings):
    backend = make_backend(settings)
    lease = SlotLease(0, "one")
    backend.process = type("Process", (), {"pid": 1})()
    assert not backend.completion_payload({"cache_prompt": True}, lease)["cache_prompt"]


async def test_cancelled_lease_invalidates_only_its_slot(settings):
    backend = make_backend(settings)
    identity = CacheIdentity("single-operator", "m", "t", "b", 2048, "f16", "rope")
    for cache in backend._prefixes.values():
        cache.remember(identity, (1, 2, 3))
    slot = await backend._available.get()
    lease = SlotLease(slot, "cancelled")
    backend._leases[slot] = lease
    backend._release(lease)
    assert not backend._prefixes[slot].tokens
    assert backend._prefixes[1 - slot].tokens == (1, 2, 3)


def test_per_slot_limits_cover_at_most_the_configured_logical_budget(settings):
    backend = make_backend(settings)
    assert (
        sum(cache.limit_bytes for cache in backend._prefixes.values())
        <= settings.cache_limit_mb * 1024**2
    )
    assert backend._prefixes[0] is not backend._prefixes[1]
