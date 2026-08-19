"""Persistence for runtime settings changed through the drawer (US-8).

Model selection was in-memory only, so every backend restart dropped it and the
next request failed with "no model selected for the 'triage' role". Nothing in
the PRD required persistence - US-8 only asks that settings change without a
restart - but an operator re-picking three models after every restart is a
demo-day trip hazard, and the eval CLI cannot run at all without them.

Written to the data directory rather than to `.env`: `.env` is the operator's
file and may be under version control at their site, whereas the data directory
is already gitignored and already holds derived state.

The API key is deliberately NOT persisted. A key written to disk by a UI action
is a credential the operator did not knowingly store; it stays in memory and in
`.env`, where they put it on purpose.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import MODEL_ROLES, get_settings
from app.logging_setup import get_logger

log = get_logger("settings_store")

FILENAME = "runtime_settings.json"
PERSISTED = ("gateway_url", "gateway_enabled", "ssl_verify")


def _path():
    settings = get_settings()
    settings.ensure_dirs()
    return settings.data_dir / FILENAME


def save() -> None:
    """Snapshot the persistable fields. Never raises - failing to save a
    preference must not fail the request that changed it."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "models": settings.configured_models,
        **{field: getattr(settings, field) for field in PERSISTED},
    }
    try:
        _path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("runtime_settings_saved", models=payload["models"])
    except OSError as exc:
        log.warning("runtime_settings_save_failed", error=str(exc))


def load() -> dict[str, Any]:
    """Apply the saved snapshot at boot.

    An explicit MODEL_* in the environment WINS: an operator who set it in .env
    for an unattended run should not have it silently overridden by whatever was
    last clicked in the drawer.
    """
    path = _path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("runtime_settings_load_failed", error=str(exc))
        return {}

    settings = get_settings()
    applied: list[str] = []

    for role, alias in (payload.get("models") or {}).items():
        if role in MODEL_ROLES and alias and not settings.configured_models[role]:
            settings.set_model(role, alias)
            applied.append(role)

    for field in PERSISTED:
        if field in payload and payload[field] is not None:
            setattr(settings, field, payload[field])

    if applied:
        log.info("runtime_settings_restored", roles=applied)
    return payload
