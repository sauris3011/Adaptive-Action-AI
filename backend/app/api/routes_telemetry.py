"""Telemetry endpoints backing the header monitor (FR-13)."""

from __future__ import annotations

from fastapi import APIRouter

from app.llm import ledger
from app.schemas.api import TelemetrySummary

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/summary", response_model=TelemetrySummary)
def summary() -> TelemetrySummary:
    return TelemetrySummary(**ledger.summary())


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
