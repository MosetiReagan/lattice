"""Reuse immutable verified transport configuration, not request or tenant state."""

from functools import lru_cache
from ssl import SSLContext

import httpx


@lru_cache(maxsize=1)
def native_ssl_context() -> SSLContext:
    """Avoid reloading trust roots for every private loopback HTTP client.

    Clients remain request-scoped and cancellation-safe. No connections, headers,
    prompts, credentials or cache state are shared. Verification stays enabled;
    environment proxies and trust-root overrides remain disabled as before.
    """
    return httpx.create_ssl_context(verify=True, trust_env=False)
