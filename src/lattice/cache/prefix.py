"""Single-slot prefix eligibility, exact identity and byte-bounded logical leases."""

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheIdentity:
    tenant: str
    model_sha256: str
    tokenizer_sha256: str
    backend_sha256: str
    context_tokens: int
    kv_type: str
    positional_configuration: str


@dataclass(frozen=True)
class CacheDecision:
    reuse: bool
    prefix_tokens: int
    reason: str


class PrefixCache:
    """Tracks one native slot, never copies tensors or caches response text.

    Byte limits describe eligible dense KV, not native physical pool allocation.
    Reusing a hash alone is insufficient: exact prefix token IDs are compared.
    """

    def __init__(
        self,
        limit_bytes: int,
        bytes_per_token: int,
        min_tokens: int = 64,
        ttl_seconds: float = 300,
    ):
        if min(limit_bytes, bytes_per_token, min_tokens) <= 0 or ttl_seconds <= 0:
            raise ValueError("Cache limits must be positive")
        self.limit_bytes, self.bytes_per_token, self.min_tokens = (
            limit_bytes,
            bytes_per_token,
            min_tokens,
        )
        self.ttl_seconds = ttl_seconds
        self.identity = None
        self.tokens = ()
        self.created = 0.0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.reused_tokens = 0

    def invalidate(self):
        if self.tokens:
            self.evictions += 1
        self.identity, self.tokens, self.created = None, (), 0.0

    def plan(
        self, identity: CacheIdentity, tokens: tuple[int, ...], now: float | None = None
    ) -> CacheDecision:
        now = time.monotonic() if now is None else now
        if self.tokens and (
            identity != self.identity or now - self.created > self.ttl_seconds
        ):
            self.invalidate()
        common = 0
        if identity == self.identity:
            for previous, current in zip(self.tokens, tokens, strict=False):
                if previous != current:
                    break
                common += 1
        # Backend must evaluate at least the final prompt token to recover logits.
        common = min(
            common, max(0, len(tokens) - 1), self.limit_bytes // self.bytes_per_token
        )
        reuse = common >= self.min_tokens
        if reuse:
            self.hits += 1
        else:
            self.misses += 1
        return CacheDecision(
            reuse,
            common if reuse else 0,
            "identical compatible prefix"
            if reuse
            else "cold, short or incompatible prefix",
        )

    def remember(
        self, identity: CacheIdentity, tokens: tuple[int, ...], now: float | None = None
    ):
        maximum = self.limit_bytes // self.bytes_per_token
        if len(tokens) > maximum:
            # No promise to surgically evict part of the native slot: decline reuse entirely.
            self.invalidate()
            return
        self.identity, self.tokens, self.created = (
            identity,
            tokens,
            time.monotonic() if now is None else now,
        )

    def observe(self, native_reused_tokens: int):
        self.reused_tokens += max(0, native_reused_tokens)

    def stats(self) -> dict:
        return {
            "eligible_hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "native_reused_tokens": self.reused_tokens,
            "logical_tokens": len(self.tokens),
            "logical_kv_bytes": len(self.tokens) * self.bytes_per_token,
            "physical_pool_bytes": None,
            "physical_allocator": "llama.cpp",
        }
