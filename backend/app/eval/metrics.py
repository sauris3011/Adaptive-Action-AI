"""KPI aggregation against the PRD 9.1 and 9.2 targets.

Each KPI carries its target and a pass flag, so the output is a verdict rather
than a table of numbers someone still has to interpret. The baselines in 9.1
(~11 minutes, ~6 system switches) are STATED ASSUMPTIONS, not measurements, and
are labelled as such in the output - PRD 9.3 requires that they never be
presented as observed.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.eval.scoring import CaseScore

# PRD 9.3: framing assumptions, never presented as measured.
ASSUMED_BASELINE = {
    "task_completion_seconds": 660,
    "system_switches": 6,
    "measured": False,
    "note": "Stated assumptions used to frame improvement. No user study was run.",
}


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _kpi(name: str, value: float, target: float, unit: str, passed: bool,
         detail: str = "") -> dict[str, Any]:
    return {"name": name, "value": value, "target": target, "unit": unit,
            "pass": passed, "detail": detail}


def summarise(scores: list[CaseScore], telemetry: dict[str, Any],
              warm: dict[str, Any] | None = None) -> dict[str, Any]:
    total = len(scores)
    completed = [s for s in scores if not s.error]
    latencies = [s.latency_ms for s in completed]

    conflict_cases = [s for s in scores if s.ok_conflict is not None]
    conflict_hits = sum(1 for s in conflict_cases if s.ok_conflict)

    # The headline metric is C1-C3 specifically (PRD 9.1), not every conflict.
    canonical = [s for s in conflict_cases if s.conflict_id in ("C1", "C2", "C3")]
    canonical_hits = sum(1 for s in canonical if s.ok_conflict)

    deadline_cases = [s for s in scores if s.ok_deadline is not None]
    deadline_hits = sum(1 for s in deadline_cases if s.ok_deadline)

    cited_any = sum(1 for s in completed if s.ok_citation_any)
    cited_right = sum(1 for s in completed if s.ok_citation_correct)
    correct_action = sum(1 for s in completed if s.ok_action)
    automated = sum(1 for s in scores if s.automated)
    passed = sum(1 for s in scores if s.passed)

    p95 = _percentile(latencies, 0.95)
    # Judged on the warm pass. The scored pass runs cold on purpose, so its hit
    # ratio is near zero by construction and says nothing about the cache.
    cache_source = warm or telemetry
    cache_ratio = round(100.0 * cache_source.get("cache_hit_ratio", 0.0), 1)

    product = [
        _kpi("Task completion time", round(p95 / 1000, 1), 90.0, "s p95", p95 <= 90_000,
             f"vs an assumed {ASSUMED_BASELINE['task_completion_seconds']}s manual baseline"),
        _kpi("Automation rate", _pct(automated, total), 60.0, "%", _pct(automated, total) >= 60.0,
             "correct action produced without escalation"),
        _kpi("Resolution quality", _pct(correct_action, total), 85.0, "%",
             _pct(correct_action, total) >= 85.0, "action matches the labelled expectation"),
        _kpi("Citation presence", _pct(cited_any, total), 100.0, "%",
             _pct(cited_any, total) >= 100.0, "cites at least one clause"),
        _kpi("Citation precision", _pct(cited_right, total), 90.0, "%",
             _pct(cited_right, total) >= 90.0, "cites the governing clause"),
        _kpi("Conflict detection recall", _pct(canonical_hits, len(canonical)), 100.0, "%",
             len(canonical) > 0 and canonical_hits == len(canonical),
             f"C1-C3 only; {conflict_hits}/{len(conflict_cases)} across all conflict cases"),
        _kpi("Compliance adherence", _pct(deadline_hits, len(deadline_cases)), 100.0, "%",
             len(deadline_cases) > 0 and deadline_hits == len(deadline_cases),
             "states the applicable deadline where one applies"),
        _kpi("User effort", 2.0, 2.0, "interactions", True,
             "review plus approve; structural, not measured per case"),
    ]

    technical = [
        _kpi("Cache hit ratio", cache_ratio, 30.0, "%", cache_ratio >= 30.0,
             "measured on a repeat pass; the scored pass runs cold so its latency is real"),
        _kpi("Unhandled exceptions", len(scores) - len(completed), 0.0, "cases",
             len(completed) == total, "a case that raised rather than answering"),
        _kpi("Grounded calls with context", _pct(sum(1 for s in completed if s.grounded), total),
             100.0, "%", all(s.grounded for s in completed),
             "guard-enforced; a GROUNDED call with empty context cannot run"),
        _kpi("Cases passing all checks", _pct(passed, total), 85.0, "%",
             _pct(passed, total) >= 85.0, "every scored dimension correct"),
    ]

    return {
        "cases": total,
        "passed": passed,
        "product_kpis": product,
        "technical_kpis": technical,
        "all_targets_met": all(k["pass"] for k in product + technical),
        "assumed_baseline": ASSUMED_BASELINE,
        "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": p95,
                       "max": max(latencies) if latencies else 0},
        "telemetry": telemetry,
        "warm_pass": warm,
        "case_results": [asdict(s) for s in scores],
    }
