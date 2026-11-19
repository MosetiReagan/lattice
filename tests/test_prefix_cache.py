from dataclasses import replace

import pytest

from lattice.cache.prefix import CacheIdentity, PrefixCache


def identity():
    return CacheIdentity(
        "tenant-a", "model", "tokenizer", "backend", 2048, "f16", "rope-default"
    )


def test_identical_prefix_and_suffix_change():
    cache = PrefixCache(2048, 8, min_tokens=4)
    original = tuple(range(10))
    cache.remember(identity(), original, now=0)
    assert cache.plan(identity(), original, now=1).prefix_tokens == 9
    assert cache.plan(identity(), (*range(8), 99), now=1).prefix_tokens == 8
    assert not cache.plan(identity(), (9, 8, 7), now=1).reuse


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant", "other"),
        ("model_sha256", "other"),
        ("tokenizer_sha256", "other"),
        ("backend_sha256", "other"),
        ("context_tokens", 1024),
        ("kv_type", "q8"),
        ("positional_configuration", "other"),
    ],
)
def test_every_identity_dimension_isolates(field, value):
    cache = PrefixCache(2048, 8, min_tokens=4)
    cache.remember(identity(), tuple(range(10)), now=0)
    assert not cache.plan(
        replace(identity(), **{field: value}), tuple(range(10)), now=1
    ).reuse
    assert cache.stats()["evictions"] == 1


def test_limit_ttl_and_lifecycle():
    cache = PrefixCache(80, 8, min_tokens=4, ttl_seconds=5)
    cache.remember(identity(), tuple(range(11)), now=0)
    assert cache.stats()["logical_tokens"] == 0
    cache.remember(identity(), tuple(range(10)), now=0)
    assert not cache.plan(identity(), tuple(range(10)), now=6).reuse
    cache.remember(identity(), tuple(range(10)), now=7)
    cache.invalidate()
    assert not cache.tokens
