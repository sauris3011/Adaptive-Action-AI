"""Eval runner.

Runs the reasoning pipeline only - triage through recommend - and stops at the
approval gate. It never approves, so a full eval run leaves no core-banking
effects behind. PRD 9.1 measures the quality of the recommendation; approving
twenty synthetic disputes would only measure that the mock API works, which
Stage 4 already established.

Cases run in-process against the graph rather than over HTTP. There is no
server to depend on, which is what lets the eval be part of a pre-flight or a
CI step later.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from app.config import REPO_ROOT
from app.db.engine import connect, query_one
from app.eval.metrics import summarise
from app.eval.scoring import CaseScore, score_case
from app.logging_setup import get_logger

log = get_logger("eval.harness")

CASES_PATH = REPO_ROOT / "backend" / "domain" / "banking" / "eval_cases.json"


def clear_prompt_cache() -> int:
    """Start the scored pass from a cold cache.

    Without this the eval is not measuring what it claims to. The prompt cache
    persists across runs, so a second eval replays the first from cache and
    reports a p95 of two seconds and a cost of zero - numbers that describe the
    cache, not the system. Cold-starting makes the scored pass an honest
    measurement and leaves the warm pass to measure the cache.
    """
    with connect() as conn:
        removed = conn.execute("SELECT count(*) AS c FROM llm_cache").fetchone()["c"]
        conn.execute("DELETE FROM llm_cache")
    log.info("prompt_cache_cleared", entries=removed)
    return removed


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    data = json.loads((path or CASES_PATH).read_text(encoding="utf-8"))
    return data["cases"]


def _telemetry_snapshot() -> dict[str, Any]:
    """Read the ledger directly rather than over HTTP - the eval must not need
    a running server."""
    row = query_one(
        "SELECT count(*) AS calls, "
        "COALESCE(sum(prompt_tokens),0) AS input_tokens, "
        "COALESCE(sum(completion_tokens),0) AS output_tokens, "
        "COALESCE(sum(cost_usd),0.0) AS cost_usd, "
        "COALESCE(sum(cache_hit),0) AS cache_hits, "
        "COALESCE(sum(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END),0) AS errors "
        "FROM llm_calls"
    ) or {}
    return {k: (v or 0) for k, v in row.items()}


def _telemetry_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    calls = after["calls"] - before["calls"]
    hits = after["cache_hits"] - before["cache_hits"]
    return {
        "llm_calls": calls,
        "input_tokens": after["input_tokens"] - before["input_tokens"],
        "output_tokens": after["output_tokens"] - before["output_tokens"],
        "estimated_cost_usd": round(after["cost_usd"] - before["cost_usd"], 6),
        "cache_hits": hits,
        "cache_misses": calls - hits,
        "cache_hit_ratio": round(hits / calls, 4) if calls else 0.0,
        "errors": after["errors"] - before["errors"],
    }


def _run_case(case: dict[str, Any], runner: Callable[..., dict[str, Any]]) -> CaseScore:
    started = time.perf_counter()
    try:
        run = runner(
            case["text"],
            transaction_id=case.get("transaction_id"),
            customer_id=case.get("customer_id"),
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        return score_case(case, _serialise(run), None, elapsed)
    except Exception as exc:  # noqa: BLE001 - a failed case is a result, not a crash
        elapsed = int((time.perf_counter() - started) * 1000)
        log.warning("eval_case_failed", case=case["id"], error=str(exc))
        return score_case(case, None, f"{type(exc).__name__}: {exc}", elapsed)


def _serialise(state: dict[str, Any]) -> dict[str, Any]:
    """Flatten the graph state into the shape scoring.py expects."""
    recommendation = state.get("recommendation")
    reconciliation = state.get("reconciliation")
    grounding = state.get("grounding")
    return {
        "recommendation": recommendation.model_dump(mode="json") if recommendation else None,
        "reconciliation": reconciliation.model_dump(mode="json") if reconciliation else None,
        "evidence": [e.model_dump(mode="json") for e in grounding.evidence] if grounding else [],
    }


def run_eval(
    cases: list[dict[str, Any]] | None = None,
    *,
    warm_pass: bool = True,
    cold_start: bool = True,
    progress: Callable[[int, int, CaseScore], None] | None = None,
) -> dict[str, Any]:
    """Score every case, then optionally repeat the run to measure the cache.

    The scored pass runs cold, so its latency and cost are real. The warm pass
    then re-runs the same cases, which is exactly the repeat-query behaviour the
    cache exists for - twenty DISTINCT prompts against a cold cache produce a hit
    ratio near zero by construction, so measuring the cache on the scored pass
    would say nothing about whether caching works. Only the FIRST pass scores
    correctness; counting a case twice would inflate the denominator.
    """
    from app.agents import graph as agent_graph

    cases = cases or load_cases()
    cleared = clear_prompt_cache() if cold_start else 0
    before = _telemetry_snapshot()
    scores: list[CaseScore] = []

    for index, case in enumerate(cases, start=1):
        score = _run_case(case, agent_graph.run)
        scores.append(score)
        log.info("eval_case", case=case["id"], passed=score.passed,
                 action=score.produced_action, latency_ms=score.latency_ms)
        if progress:
            progress(index, len(cases), score)

    warm: dict[str, Any] | None = None
    if warm_pass:
        warm_before = _telemetry_snapshot()
        for case in cases:
            _run_case(case, agent_graph.run)
        warm = _telemetry_delta(warm_before, _telemetry_snapshot()) | {
            "note": "second identical pass; measures the cache on repeat queries",
        }

    telemetry = _telemetry_delta(before, _telemetry_snapshot())
    telemetry["cold_start"] = cold_start
    telemetry["cache_entries_cleared"] = cleared
    report = summarise(scores, telemetry, warm)
    report["cold_start"] = cold_start
    return report
