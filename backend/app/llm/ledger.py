"""Telemetry ledger - the source of truth for the header monitor (PRD 5.8).

Every LLM call lands here synchronously. The UI reads THIS, not LiteLLM /spend
and not LangSmith, because an always-visible element must not depend on a SaaS
round trip through a TLS-intercepting proxy.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from app.db.engine import connect, query_one
from app.llm.pricing import estimate_cost
from app.logging_setup import get_logger

log = get_logger("llm.ledger")

# In-flight gauge. A counter rather than a DB read because "active calls" is a
# point-in-time value that never needs to survive a restart.
_inflight = 0
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InFlight:
    """Context manager maintaining the active-call gauge."""

    def __enter__(self) -> "InFlight":
        global _inflight
        with _lock:
            _inflight += 1
        return self

    def __exit__(self, *exc: Any) -> None:
        global _inflight
        with _lock:
            _inflight = max(0, _inflight - 1)


def active_calls() -> int:
    with _lock:
        return _inflight


def record(
    *,
    model: str,
    call_class: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    cache_hit: bool = False,
    run_id: str | None = None,
    node: str | None = None,
    exemption_reason: str | None = None,
    error: str | None = None,
) -> None:
    total = prompt_tokens + completion_tokens
    # A cache hit costs nothing; charging for it would misreport the saving.
    cost = 0.0 if cache_hit else estimate_cost(model, prompt_tokens, completion_tokens)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO llm_calls (ts, run_id, node, call_class, exemption_reason, model,
                                   prompt_tokens, completion_tokens, total_tokens,
                                   cost_usd, latency_ms, cache_hit, error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (_now(), run_id, node, call_class, exemption_reason, model,
             prompt_tokens, completion_tokens, total, cost, latency_ms,
             1 if cache_hit else 0, error),
        )
    log.info(
        "llm_call",
        model=model,
        node=node,
        call_class=call_class,
        exemption_reason=exemption_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost, 6),
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        error=error,
    )


def summary() -> dict[str, Any]:
    """Feeds the global header monitor (FR-13) and the settings drawer (FR-14)."""
    row = query_one(
        """
        SELECT COUNT(*)                      AS calls,
               COALESCE(SUM(prompt_tokens),0)     AS input_tokens,
               COALESCE(SUM(completion_tokens),0) AS output_tokens,
               COALESCE(SUM(cost_usd),0.0)        AS cost_usd,
               COALESCE(SUM(cache_hit),0)         AS cache_hits,
               COALESCE(SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END),0) AS errors
        FROM llm_calls
        """
    ) or {}
    calls = int(row.get("calls", 0))
    hits = int(row.get("cache_hits", 0))
    return {
        "active_calls": active_calls(),
        "total_calls": calls,
        "input_tokens": int(row.get("input_tokens", 0)),
        "output_tokens": int(row.get("output_tokens", 0)),
        "total_tokens": int(row.get("input_tokens", 0)) + int(row.get("output_tokens", 0)),
        "estimated_cost_usd": round(float(row.get("cost_usd", 0.0)), 6),
        "cache_hits": hits,
        "cache_misses": calls - hits,
        "cache_hit_ratio": round(hits / calls, 4) if calls else 0.0,
        "errors": int(row.get("errors", 0)),
    }


def trace(run_id: str, node: str, event: str, payload: Any = None) -> None:
    """Audit trail for FR-9 - every decision reconstructable from SQLite alone."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_events (run_id, ts, node, event, payload) VALUES (?,?,?,?,?)",
            (run_id, _now(), node, event,
             json.dumps(payload, default=str) if payload is not None else None),
        )
