"""Live model catalogue from the LiteLLM gateway (US-8).

Model routing is chosen in the UI, not baked into .env, so the catalogue has to
come from the gateway itself. GET {gateway}/v1/models is the OpenAI-compatible
discovery surface LiteLLM exposes; anything it does not list cannot be routed to.

Probing is explicit (the user presses a button) rather than automatic on boot:
an unreachable gateway must never slow down or fail application startup.
"""

from __future__ import annotations

from app.config import get_settings
from app.logging_setup import get_logger
from app.tls import build_http_client

log = get_logger("llm.catalog")

# Heuristic only: used to sort likely embedding models to the top of the embed
# dropdown. The gateway does not report model capability, so this never filters
# - a model missing from the heuristic is still selectable for any role.
_EMBED_MARKERS = ("embed", "embedding")


def looks_like_embedding(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(marker in lowered for marker in _EMBED_MARKERS)


def probe_models(timeout: float = 15.0) -> list[str]:
    """Return every model id the gateway offers.

    Raises RuntimeError with a message fit for the settings drawer - this is the
    one place the user finds out their gateway URL or key is wrong.
    """
    settings = get_settings()
    url = f"{settings.openai_base_url}/models"
    headers = {"Authorization": f"Bearer {settings.gateway_api_key}"} if settings.gateway_api_key else {}

    try:
        with build_http_client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the UI
        hint = "" if not settings.ssl_verify else (
            " (if this is a TLS error behind the corporate proxy, disable SSL "
            "verification below)"
        )
        raise RuntimeError(f"Cannot reach {url}: {exc}{hint}") from exc

    if resp.status_code == 401:
        raise RuntimeError(f"{url} rejected the API key (HTTP 401). Check the key above.")
    if resp.status_code != 200:
        raise RuntimeError(f"{url} returned HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{url} did not return JSON: {resp.text[:200]}") from exc

    ids = sorted({
        str(entry.get("id", "")).strip()
        for entry in payload.get("data", [])
        if str(entry.get("id", "")).strip()
    })
    log.info("model_catalogue_probed", url=url, count=len(ids))
    return ids
