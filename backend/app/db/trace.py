"""Run trace (FR-9, FR-24).

Every decision must be reconstructable from SQLite alone, with no dependency on
any SaaS trace (PRD 7.3). LangGraph's checkpointer stores state for resumption;
this stores the narrative - what each node did and when - which is what an
auditor reads.

Writes never raise. A failed audit write must not fail the user's request; it is
logged instead, which is itself visible in the structured log.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.engine import connect, query_all
from app.logging_setup import get_logger

log = get_logger("db.trace")


def record(run_id: str, node: str, event: str, payload: dict[str, Any] | None = None) -> None:
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO run_events (run_id, ts, node, event, payload) VALUES (?,?,?,?,?)",
                (run_id, datetime.now(timezone.utc).isoformat(), node, event,
                 json.dumps(payload or {}, default=str)),
            )
    except Exception as exc:  # noqa: BLE001 - auditing must not break the request
        log.warning("trace_write_failed", run_id=run_id, node=node, error=str(exc))
    # `event` is structlog's own name for the log message, and payload keys are
    # caller-supplied - both are namespaced rather than splatted so an audit
    # field can never collide with a logging field.
    log.info("run_event", run_id=run_id, node=node, step=event, detail=payload or {})


def events(run_id: str) -> list[dict[str, Any]]:
    rows = query_all(
        "SELECT ts, node, event, payload FROM run_events WHERE run_id = ? ORDER BY id",
        (run_id,),
    )
    for row in rows:
        try:
            row["payload"] = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError:
            row["payload"] = {}
    return rows


def runs(limit: int = 25) -> list[dict[str, Any]]:
    return query_all(
        "SELECT run_id, min(ts) AS started_at, max(ts) AS ended_at, count(*) AS events "
        "FROM run_events GROUP BY run_id ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )
