"""Graph-backend drill (acceptance criterion 9, PRD 9.2).

Two things, in order:

1. **Fallback selection.** With no Neo4j credentials, selection must land on
   Kuzu and say why. This is the criterion-9 requirement and it runs anywhere.
2. **Contract test.** The five-query surface is exercised against whichever
   backend was selected and compared to values derived from the data itself -
   the fixture for entities, SQLite for disputes - not to values recorded from a
   previous run. Both backends must return the same answers or the fallback is
   not a fallback.

Run it twice to satisfy "passes on both backends":

    python backend/scripts/backend_drill.py                    # selects Kuzu
    GRAPH_BACKEND=neo4j python backend/scripts/backend_drill.py

The second form needs Aura credentials in .env. Without them it exits 2 saying
so, rather than passing silently on one backend and implying it checked two.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import records as record_store  # noqa: E402
from app.db.models import migrate  # noqa: E402
from app.graph import extract  # noqa: E402
from app.graph.base import (  # noqa: E402
    active_backend,
    close_store,
    get_store,
    probe_neo4j,
    select_backend,
)
from app.logging_setup import configure_logging  # noqa: E402

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


class Drill:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, name: str, actual: Any, expected: Any) -> None:
        self.checks += 1
        ok = actual == expected
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {name}")
        if not ok:
            print(f"        {DIM}expected {expected!r}, got {actual!r}{RESET}")
            self.failures.append(f"{name}: expected {expected!r}, got {actual!r}")

    def check_that(self, name: str, predicate: bool, detail: str = "") -> None:
        self.checks += 1
        mark = f"{GREEN}PASS{RESET}" if predicate else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {name}")
        if not predicate:
            print(f"        {DIM}{detail}{RESET}")
            self.failures.append(f"{name}: {detail}")


def _expected_counts(fixture: dict[str, Any]) -> dict[str, int]:
    """Derived from the data, so an edit to it cannot silently make the drill
    assert stale numbers.

    Disputes are counted from SQLite rather than from the fixture: the graph
    projects them from there, and a dispute raised at runtime is a real node the
    drill must expect rather than a failure it should report.
    """
    return {
        "Customer": len(fixture["customers"]),
        "Account": len(fixture["accounts"]),
        "Merchant": len(fixture["merchants"]),
        "Transaction": len(fixture["transactions"]),
        "Dispute": record_store.counts()["dispute_history"],
    }


def run_contract(drill: Drill, fixture: dict[str, Any]) -> None:
    store = get_store()
    counts = store.counts()
    expected = _expected_counts(fixture)

    print(f"\nNode counts ({active_backend()})")
    for label, want in expected.items():
        drill.check(f"{label} nodes", counts["by_label"].get(label), want)
    drill.check_that("Policy nodes present", counts["by_label"].get("Policy", 0) > 0,
                     "no Policy nodes; run seed_data.py first")

    print("\nFive-query surface")

    # 1. customer_dispute_history
    cust = "CUST-1002"
    want_disputes = len(record_store.disputes_for_customer(cust))
    history = store.customer_dispute_history(cust)
    drill.check(f"customer_dispute_history({cust}) rows", len(history), want_disputes)
    drill.check_that("dispute history ordered newest first",
                     [r["opened_at"] for r in history] == sorted(
                         [r["opened_at"] for r in history], reverse=True),
                     f"got {[r['opened_at'] for r in history]}")

    # 2. merchant_risk_profile
    merchant = "MERCH-201"
    want_txns = sum(1 for t in fixture["transactions"] if t["merchant_id"] == merchant)
    profile = store.merchant_risk_profile(merchant)
    drill.check_that("merchant_risk_profile returns a row", profile is not None, "got None")
    if profile:
        drill.check("merchant risk_band", profile["risk_band"], "elevated")
        drill.check("merchant transaction_count", int(profile["transaction_count"]), want_txns)
    drill.check("merchant_risk_profile(unknown) is None",
                store.merchant_risk_profile("MERCH-000"), None)

    # 3. policy_dependencies
    deps = store.policy_dependencies("PCT-7.1")
    outgoing = {(d["clause_id"], d["relation"]) for d in deps if d["direction"] == "outgoing"}
    drill.check_that("policy_dependencies(PCT-7.1) includes SUPERSEDES BDP-4.2",
                     ("BDP-4.2", "SUPERSEDES") in outgoing, f"got {sorted(outgoing)}")
    fraud_deps = store.policy_dependencies("BDP-2.1")
    incoming = {(d["clause_id"], d["relation"]) for d in fraud_deps if d["direction"] == "incoming"}
    drill.check_that("policy_dependencies(BDP-2.1) shows FSP-1.2 SUPERSEDES it",
                     ("FSP-1.2", "SUPERSEDES") in incoming, f"got {sorted(incoming)}")

    # 4. transaction_context - the fraud flag is the whole point of C3
    for txn in ("TXN-9001", "TXN-9002"):
        record = next(t for t in fixture["transactions"] if t["transaction_id"] == txn)
        context = store.transaction_context(txn)
        drill.check_that(f"transaction_context({txn}) returns a row",
                         context is not None, "got None")
        if context:
            drill.check(f"{txn} fraud_flag", int(context["fraud_flag"]), record["fraud_flag"])
            drill.check(f"{txn} amount", float(context["amount"]), float(record["amount"]))
            drill.check(f"{txn} merchant_id", context["merchant_id"], record["merchant_id"])
    drill.check("transaction_context(unknown) is None",
                store.transaction_context("TXN-0000"), None)

    # 5. neighborhood
    hood = store.neighborhood("TXN-9001", 2)
    ids = {n["id"] for n in hood["nodes"]}
    drill.check_that("neighborhood(TXN-9001) reaches its account and merchant",
                     {"ACC-5001", "MERCH-203"} <= ids, f"got {sorted(ids)}")
    drill.check_that("neighborhood(TXN-9001) reaches the cardholder at 2 hops",
                     "CUST-1001" in ids, f"got {sorted(ids)}")
    drill.check("neighborhood(unknown) reports not found",
                store.neighborhood("NOPE", 2)["found"], False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Graph backend fallback and contract drill")
    parser.add_argument("--out", default="", help="optional path to write the JSON result")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    migrate()
    drill = Drill()

    print("Graph backend drill")
    print("=" * 60)
    reachable, detail = probe_neo4j()
    print(f"GRAPH_BACKEND setting : {settings.graph_backend}")
    print(f"Neo4j credentials     : {'set' if settings.neo4j_uri else 'not set'}")
    print(f"Neo4j reachability    : {detail}")

    if settings.graph_backend == "neo4j" and not reachable:
        print(f"\n{RED}Cannot run the Neo4j leg:{RESET} {detail}")
        print("Set NEO4J_URI / NEO4J_PASSWORD in .env, or run without GRAPH_BACKEND=neo4j.")
        return 2

    print("\nSelection (criterion 9)")
    try:
        chosen = select_backend()
    except RuntimeError as exc:
        print(f"  {RED}FAIL{RESET}  selection raised: {exc}")
        return 1

    if settings.graph_backend == "auto" and not reachable:
        drill.check("auto selection falls back to Kuzu when Neo4j is unreachable",
                    chosen, "kuzu")
    else:
        drill.check_that(f"selection resolved to {chosen}", bool(chosen), "no backend selected")

    fixture = extract.load_records()
    try:
        run_contract(drill, fixture)
    finally:
        close_store()

    passed = not drill.failures
    print("\n" + "=" * 60)
    print(f"{GREEN if passed else RED}{'PASS' if passed else 'FAIL'}{RESET}  "
          f"{drill.checks - len(drill.failures)}/{drill.checks} checks on backend "
          f"'{chosen}'")
    if not passed:
        for failure in drill.failures:
            print(f"  - {failure}")
    else:
        print(f"{DIM}Run again with GRAPH_BACKEND=neo4j to cover the second backend.{RESET}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "backend": chosen, "checks": drill.checks,
            "failures": drill.failures, "passed": passed,
        }, indent=2), encoding="utf-8")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
