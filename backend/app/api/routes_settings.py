"""Settings drawer endpoints (FR-14, US-8).

Gateway URL/key and the SSL flag are mutable at runtime so the demo can be
repointed without a restart. Mutating settings invalidates the cached model
clients, otherwise the change would silently not take effect.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.graph.base import active_backend
from app.llm.factory import get_model
from app.schemas.api import RuntimeSettings, RuntimeSettingsPatch
from app.logging_setup import get_logger
from app.tls import tls_warning

log = get_logger("api.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current() -> RuntimeSettings:
    s = get_settings()
    return RuntimeSettings(
        gateway_url=s.gateway_url,
        gateway_api_key_set=bool(s.gateway_api_key),
        ssl_verify=s.ssl_verify,
        tls_warning=tls_warning(),
        models=s.configured_models,
        graph_backend=active_backend(),
    )


@router.get("", response_model=RuntimeSettings)
def read_settings() -> RuntimeSettings:
    return _current()


@router.patch("", response_model=RuntimeSettings)
def update_settings(patch: RuntimeSettingsPatch) -> RuntimeSettings:
    s = get_settings()
    changed: list[str] = []

    if patch.gateway_url is not None:
        s.gateway_url = patch.gateway_url.rstrip("/")
        changed.append("gateway_url")
    if patch.gateway_api_key is not None:
        s.gateway_api_key = patch.gateway_api_key
        changed.append("gateway_api_key")
    if patch.ssl_verify is not None:
        s.ssl_verify = patch.ssl_verify
        changed.append("ssl_verify")

    if changed:
        # Cached clients hold the old base_url / key / TLS policy.
        get_model.cache_clear()
        log.warning("runtime_settings_changed", fields=changed,
                    ssl_verify=s.ssl_verify)

    return _current()
