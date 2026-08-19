"""Telemetry endpoints backing the header monitor (FR-13)."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.graph.base import active_backend
from app.llm import ledger
from app.schemas.api import TelemetrySummary

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/summary", response_model=TelemetrySummary)
def summary() -> TelemetrySummary:
    """Ledger totals plus the two health facts the header shows.

    `graph_fallback` is stated rather than inferred from the backend name: which
    store is a fallback is a deployment question, and the UI should not have to
    know that "kuzu" means degraded.
    """
    backend = active_backend()
    settings = get_settings()
    return TelemetrySummary(
        **ledger.summary(),
        graph_backend=backend,
        graph_fallback=backend == "kuzu" and settings.graph_backend != "kuzu",
        gateway_enabled=settings.gateway_enabled,
    )


@router.get("/recent")
def recent(limit: int = 25) -> list[dict]:
    """Recent calls for debugging and the demo narrative."""
    from app.db.engine import query_all

    return query_all(
        "SELECT ts, node, call_class, model, prompt_tokens, completion_tokens, "
        "cost_usd, latency_ms, cache_hit, error FROM llm_calls "
        "ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    )
