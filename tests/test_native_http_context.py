import ssl

from lattice.backends.http_client import native_ssl_context


def test_native_context_retains_verification_and_is_reused():
    context = native_ssl_context()
    assert context is native_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
