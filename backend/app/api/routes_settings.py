"""Settings drawer endpoints (FR-14, US-8).

Gateway URL/key, the SSL flag and model routing are all mutable at runtime so
the demo can be repointed without a restart. Mutating settings invalidates the
cached model clients, otherwise the change would silently not take effect.

Model routing is chosen from the LIVE gateway catalogue rather than from a
hardcoded list: /models is probed on demand and the drawer offers only ids the
gateway actually serves.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import MODEL_ROLES, get_settings
from app.graph.base import active_backend
from app.llm.catalog import looks_like_embedding, probe_models
from app.llm.factory import get_model
from app.schemas.api import ModelCatalog, RuntimeSettings, RuntimeSettingsPatch
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
        unconfigured_roles=s.unconfigured_roles,
        graph_backend=active_backend(),
    )


@router.get("", response_model=RuntimeSettings)
def read_settings() -> RuntimeSettings:
    return _current()


@router.get("/models", response_model=ModelCatalog)
def list_models() -> ModelCatalog:
    """Probe the gateway for the models it offers. Explicit, never on boot."""
    s = get_settings()
    try:
        available = probe_models()
    except RuntimeError as exc:
        # 502: the failure is upstream, and the message is written for the drawer.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ModelCatalog(
        gateway_url=s.gateway_url,
        models=available,
        embedding_models=[m for m in available if looks_like_embedding(m)],
        probed_at=datetime.now(timezone.utc).isoformat(),
    )


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

    if patch.models is not None:
        unknown = sorted(set(patch.models) - set(MODEL_ROLES))
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown model role(s) {unknown}; expected {list(MODEL_ROLES)}",
            )
        for role, alias in patch.models.items():
            if s.configured_models[role] != alias.strip():
                s.set_model(role, alias)
                changed.append(f"model_{role}")

    if changed:
        # Cached clients hold the old base_url / key / TLS policy / alias.
        get_model.cache_clear()
        log.warning("runtime_settings_changed", fields=changed,
                    ssl_verify=s.ssl_verify, models=s.configured_models)

    return _current()
