"""Single choke point for TLS policy.

The corporate environment intercepts certificates. When SSL_VERIFY=false every
outbound client is built with verification disabled from HERE and nowhere else,
so the blast radius of the bypass is one file and one log line.

SECURITY TRADE-OFF (PRD 7.2): with verification disabled the application cannot
distinguish the corporate proxy from a hostile man-in-the-middle. Prompts,
retrieved context and responses are exposed to anyone able to intercept the
connection. Acceptable only for a local prototype on synthetic data. The correct
production fix is to trust the corporate root CA via SSL_CERT_FILE /
REQUESTS_CA_BUNDLE, not to disable verification.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_WARNING_BANNER = (
    "TLS VERIFICATION DISABLED. Outbound traffic cannot be distinguished from a "
    "man-in-the-middle. Prototype/synthetic data only - never a production posture."
)


def tls_verify() -> bool:
    return get_settings().ssl_verify


def tls_warning() -> str | None:
    """Returned to the UI and logged at boot so the bypass is never silent."""
    return None if tls_verify() else _WARNING_BANNER


def build_http_client(*, timeout: float = 120.0, is_async: bool = False):
    """The only place an HTTP client is constructed for outbound calls."""
    kwargs = {"verify": tls_verify(), "timeout": httpx.Timeout(timeout)}
    return httpx.AsyncClient(**kwargs) if is_async else httpx.Client(**kwargs)
