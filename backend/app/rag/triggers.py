"""Record-driven retrieval expansion.

The problem this solves is C3, and it is a real architectural one rather than a
prompt-tuning one. The retrieval query is written by `triage` from the user's
words, but the fact that decides C3 - a fraud-engine flag - exists ONLY in the
transaction record. Nothing the cardholder says can pull the routing clause into
context, so a single-phase retrieval cannot resolve the conflict no matter how
good the reasoner is.

So the record gets a vote in what is retrieved. A trigger is a declarative rule:
when a field on the transaction record holds a given value, add a query. It is
deterministic - no model decides this - and it lives in the domain pack, so a
new vertical configures its own triggers rather than editing this file.

Consequence, stated plainly: retrieval is now two-phase for the triggered
queries. The three sources still fan out in parallel; the supplementary search
is a second bounded hop that runs only when a trigger actually fires.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.graph.extract import load_records
from app.logging_setup import get_logger

log = get_logger("rag.triggers")

MAX_TRIGGERED_QUERIES = 4


@lru_cache(maxsize=1)
def _triggers() -> tuple[dict[str, Any], ...]:
    return tuple(load_records().get("retrieval_triggers", []))


def _matches(rule: dict[str, Any], row: dict[str, Any]) -> bool:
    if rule["field"] not in row:
        return False
    value = row[rule["field"]]
    if value is None:
        return False

    op = rule.get("op", "truthy")
    if op == "truthy":
        return bool(value)
    if op == "equals":
        return str(value).upper() == str(rule["value"]).upper()
    if op == "lt":
        return float(value) < float(rule["value"])
    if op == "gte":
        return float(value) >= float(rule["value"])

    log.warning("unknown_trigger_op", trigger=rule.get("id"), op=op)
    return False


def fired(row: dict[str, Any] | None) -> list[dict[str, str]]:
    """Which triggers the record fires, and the queries they add."""
    if not row:
        return []
    hits = [
        {"id": rule["id"], "query": rule["query"], "why": rule.get("why", "")}
        for rule in _triggers()
        if _matches(rule, row)
    ]
    if hits:
        log.info("retrieval_triggers_fired", triggers=[h["id"] for h in hits])
    return hits[:MAX_TRIGGERED_QUERIES]


def reset() -> None:
    """Clear the cached pack, for a re-seed that edits the triggers."""
    _triggers.cache_clear()
