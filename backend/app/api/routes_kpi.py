"""KPI endpoints backing the strip in the UI (FR-18).

Two different things, deliberately kept apart:

* **Eval KPIs** are the quality numbers from the last `run_eval.py`, read from
  the JSON that run wrote. They are as old as that run and the response says so,
  because a stale KPI presented as live is worse than no KPI.
* **Live counters** are what has actually happened in this deployment - cases
  decided, approval outcomes, latency. They come from SQLite and are current.

Running the eval on demand from an HTTP request was considered and rejected: it
costs several minutes and real tokens, and a KPI strip that can be refreshed by
a page load would make an accidental refresh expensive.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.db import cases
from app.db.engine import query_one
from app.logging_setup import get_logger

router = APIRouter(prefix="/api/kpi", tags=["kpi"])
log = get_logger("api.kpi")

EVAL_FILENAME = "eval_latest.json"


def _eval_report() -> dict[str, Any] | None:
    path = get_settings().data_dir / EVAL_FILENAME
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("eval_report_unreadable", error=str(exc))
        return None
    generated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
    return {
        "generated_at": generated.isoformat(),
        "age_hours": round(age_hours, 1),
        "cases": report.get("cases", 0),
        "passed": report.get("passed", 0),
        "all_targets_met": report.get("all_targets_met", False),
        "product_kpis": report.get("product_kpis", []),
        "technical_kpis": report.get("technical_kpis", []),
        "assumed_baseline": report.get("assumed_baseline", {}),
        "latency_ms": report.get("latency_ms", {}),
    }


def _live() -> dict[str, Any]:
    by_outcome = cases.counts_by_outcome()
    decided = sum(by_outcome.values())
    approved = by_outcome.get("approved", 0)
    row = query_one(
        "SELECT COALESCE(avg(elapsed_ms),0) AS avg_ms, COALESCE(max(elapsed_ms),0) AS max_ms, "
        "COALESCE(avg(confidence),0) AS avg_confidence FROM dispute_cases"
    ) or {}
    return {
        "cases_decided": decided,
        "by_outcome": by_outcome,
        "approval_rate_pct": round(100.0 * approved / decided, 1) if decided else 0.0,
        "avg_latency_ms": int(row.get("avg_ms") or 0),
        "max_latency_ms": int(row.get("max_ms") or 0),
        "avg_confidence": round(float(row.get("avg_confidence") or 0.0), 3),
    }


@router.get("")
def kpis() -> dict[str, Any]:
    report = _eval_report()
    return {
        "eval": report,
        "live": _live(),
        # The strip renders a prompt to run the eval rather than zeros, so an
        # unrun eval never reads as a failed one.
        "eval_available": report is not None,
        "eval_command": "python backend/scripts/run_eval.py",
    }
