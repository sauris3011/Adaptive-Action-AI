"""Run the labelled eval set and emit KPI JSON (acceptance criterion 8).

    python backend/scripts/run_eval.py [--out data/eval_latest.json] [--no-warm-pass]
                                       [--case EV-01] [--quiet]

Exit code is 0 only when every PRD 9.1 and 9.2 target is met, so this is usable
as a gate rather than as a report someone has to read and interpret.

Model roles must be configured first - the eval calls the real gateway. Run the
backend and pick models in the settings drawer, or set MODEL_TRIAGE / MODEL_REASON
in .env for an unattended run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import settings_store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import migrate  # noqa: E402
from app.eval import harness  # noqa: E402
from app.eval.scoring import CaseScore  # noqa: E402
from app.graph.base import active_backend, close_store, select_backend  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402
from app.rag import store as vector_store  # noqa: E402

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def _mark(ok: bool) -> str:
    return f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"


def _print_kpis(title: str, kpis: list[dict]) -> None:
    print(f"\n{title}")
    print("-" * 78)
    for kpi in kpis:
        print(f"  {_mark(kpi['pass'])}  {kpi['name']:<28} "
              f"{kpi['value']:>8} {kpi['unit']:<14} target {kpi['target']}")
        if kpi["detail"]:
            print(f"        {DIM}{kpi['detail']}{RESET}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the eval set and emit KPI JSON")
    parser.add_argument("--out", default="backend/data/eval_latest.json",
                        help="where to write the KPI JSON")
    parser.add_argument("--no-warm-pass", action="store_true",
                        help="skip the second pass that measures the cache")
    parser.add_argument("--case", action="append",
                        help="run only these case ids (repeatable)")
    parser.add_argument("--keep-cache", action="store_true",
                        help="do not clear the prompt cache first (latency and cost "
                             "will then describe the cache, not the system)")
    parser.add_argument("--quiet", action="store_true", help="suppress per-case output")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    migrate()
    # Pick up model routing chosen in the settings drawer, so the CLI does not
    # need the roles duplicated into .env.
    settings_store.load()

    unconfigured = [r for r in settings.unconfigured_roles if r != "embed"]
    if unconfigured:
        print(f"{RED}Cannot run:{RESET} no model selected for {unconfigured}.")
        print("Pick models in the settings drawer, or set MODEL_TRIAGE / MODEL_REASON in .env.")
        return 2

    select_backend()
    if vector_store.stats()["chunks"] == 0:
        print(f"{RED}Cannot run:{RESET} the vector store is empty. "
              f"Run backend/scripts/seed_data.py first.")
        close_store()
        return 2

    cases = harness.load_cases()
    if args.case:
        wanted = set(args.case)
        cases = [c for c in cases if c["id"] in wanted]
        if not cases:
            print(f"{RED}No cases matched{RESET} {sorted(wanted)}")
            close_store()
            return 2

    print(f"graph backend : {active_backend()}")
    print(f"models        : {settings.configured_models}")
    print(f"cases         : {len(cases)}")
    print()

    def progress(index: int, total: int, score: CaseScore) -> None:
        if args.quiet:
            return
        detail = "" if score.passed else f"  {DIM}{'; '.join(score.failures)[:110]}{RESET}"
        print(f"  [{index:>2}/{total}] {_mark(score.passed)} {score.case_id} "
              f"{score.produced_action or '-':<24} {score.latency_ms/1000:>5.1f}s{detail}")

    report = harness.run_eval(cases, warm_pass=not args.no_warm_pass,
                              cold_start=not args.keep_cache, progress=progress)

    _print_kpis("PRODUCT KPIs (PRD 9.1)", report["product_kpis"])
    _print_kpis("TECHNICAL KPIs (PRD 9.2)", report["technical_kpis"])

    telemetry = report["telemetry"]
    print(f"\n{DIM}LLM calls {telemetry['llm_calls']} | "
          f"tokens {telemetry['input_tokens']}/{telemetry['output_tokens']} | "
          f"cost ${telemetry['estimated_cost_usd']:.4f} | "
          f"latency p50 {report['latency_ms']['p50']}ms p95 {report['latency_ms']['p95']}ms{RESET}")
    if report.get("warm_pass"):
        warm = report["warm_pass"]
        print(f"{DIM}warm pass: {warm['cache_hits']}/{warm['llm_calls']} cached "
              f"({warm['cache_hit_ratio']*100:.0f}%), ${warm['estimated_cost_usd']:.4f}{RESET}")
    print(f"{DIM}Baseline note: {report['assumed_baseline']['note']}{RESET}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nKPI JSON -> {out}")

    passed = report["all_targets_met"]
    print(f"\n{_mark(passed)}  {report['passed']}/{report['cases']} cases passed every check; "
          f"all targets met: {passed}")
    close_store()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
