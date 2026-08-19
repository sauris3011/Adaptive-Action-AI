"""Dispute case outcomes (FR-9).

One row per run, written by `record` on BOTH paths. A rejection that leaves no
trace would satisfy "no side effect" while destroying the audit trail; FR-8
requires the opposite - no effect on the mock API, but the outcome and the
reason still recorded.

The row carries the governing clause and the approver, which is what makes
Aisha's reconstruction possible from SQLite alone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.engine import connect, query_all, query_one
from app.logging_setup import get_logger

log = get_logger("db.cases")


def upsert(
    *,
    case_id: str,
    run_id: str,
    customer_id: str | None,
    transaction_id: str | None,
    reason_code: str | None,
    recommendation: str,
    governing_clause: str,
    confidence: float | None,
    outcome: str,
    approver: str | None = None,
    approved_at: str | None = None,
    reject_reason: str | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    row = {
        "case_id": case_id, "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "customer_id": customer_id, "transaction_id": transaction_id,
        "reason_code": reason_code, "recommendation": recommendation,
        "governing_clause": governing_clause, "confidence": confidence,
        "outcome": outcome, "approver": approver, "approved_at": approved_at,
        "reject_reason": reject_reason, "elapsed_ms": elapsed_ms,
    }
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dispute_cases (case_id, run_id, created_at, customer_id, "
            "transaction_id, reason_code, recommendation, governing_clause, confidence, "
            "outcome, approver, approved_at, reject_reason, elapsed_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
    log.info("case_recorded", case_id=case_id, run_id=run_id, outcome=outcome,
             approver=approver, governing_clause=governing_clause)
    return row


def by_run(run_id: str) -> dict[str, Any] | None:
    return query_one("SELECT * FROM dispute_cases WHERE run_id = ?", (run_id,))


def recent(limit: int = 50) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM dispute_cases ORDER BY created_at DESC LIMIT ?", (limit,)
    )


def counts_by_outcome() -> dict[str, int]:
    rows = query_all("SELECT outcome, count(*) AS c FROM dispute_cases GROUP BY outcome")
    return {row["outcome"]: row["c"] for row in rows}
