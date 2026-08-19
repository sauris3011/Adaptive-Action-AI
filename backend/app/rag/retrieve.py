"""Hybrid retrieval fan-out (FR-2).

Three sources, queried in parallel, merged into one typed GroundingContext:

* vector     - policy passages, carrying the tier that decides precedence
* graph      - the customer/merchant/transaction neighbourhood
* relational - the authoritative transaction record, including the fraud flag

Parallel because the three are independent and the p95 budget is 90s dominated
by model latency; serialising three sub-second I/O calls would spend that budget
on nothing. Threads rather than asyncio because the Chroma, Kuzu and SQLite
clients are all synchronous.

A source that fails is logged and dropped, not raised: partial grounding still
produces a cited answer, whereas a hard failure produces none. The guard
(PRD 5.6) still refuses to run a GROUNDED call if everything came back empty.

After the fan-out there is one bounded second hop: record facts can trigger
additional policy queries (see triggers.py). Without it, a fact that exists only
in the system of record - the fraud flag - can never pull its own governing
clause into context, and conflict C3 is unresolvable however good the reasoner.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.db import records
from app.graph.base import get_store
from app.logging_setup import get_logger
from app.rag import store as vector_store
from app.rag import triggers
from app.schemas.grounding import Evidence, EvidenceKind, GroundingContext

log = get_logger("rag.retrieve")

DEFAULT_K = 6


def _policy(query: str, k: int) -> list[Evidence]:
    return vector_store.search(query, k=k)


def _relational(transaction_id: str | None) -> list[Evidence]:
    if not transaction_id:
        return []
    fact = records.transaction_facts(transaction_id)
    return [fact] if fact else []


def _graph(transaction_id: str | None, customer_id: str | None) -> list[Evidence]:
    store = get_store()
    out: list[Evidence] = []

    if transaction_id:
        context = store.transaction_context(transaction_id)
        if context:
            out.append(Evidence(
                kind=EvidenceKind.GRAPH,
                ref=f"GRAPH:{transaction_id}",
                title="Transaction neighbourhood",
                content=_render(context),
            ))
            merchant_id = context.get("merchant_id")
            if merchant_id:
                profile = store.merchant_risk_profile(str(merchant_id))
                if profile:
                    out.append(Evidence(
                        kind=EvidenceKind.GRAPH,
                        ref=f"GRAPH:{merchant_id}",
                        title="Merchant risk profile",
                        content=_render(profile),
                    ))
            customer_id = customer_id or context.get("customer_id")

    if customer_id:
        history = store.customer_dispute_history(str(customer_id))
        if history:
            body = "\n".join(
                f"- {row['opened_at']}: {row['reason_code']} "
                f"{float(row['amount'] or 0):.2f} -> {row['outcome']}"
                for row in history
            )
            out.append(Evidence(
                kind=EvidenceKind.GRAPH,
                ref=f"GRAPH:{customer_id}:disputes",
                title=f"Prior disputes for {customer_id} ({len(history)})",
                content=body,
            ))
    return out


def _clause_dependencies(clause_ids: list[str]) -> list[Evidence]:
    """Why one clause outranks another, straight from the graph.

    This is what lets `reconcile` explain a precedence decision instead of
    merely asserting one.
    """
    store = get_store()
    out: list[Evidence] = []
    for clause_id in clause_ids:
        deps = store.policy_dependencies(clause_id)
        if not deps:
            continue
        body = "\n".join(
            f"- {clause_id} {d['relation']} {d['clause_id']}"
            if d["direction"] == "outgoing"
            else f"- {d['clause_id']} {d['relation']} {clause_id}"
            + (f" ({d['note']})" if d.get("note") else "")
            for d in deps
        )
        out.append(Evidence(
            kind=EvidenceKind.GRAPH,
            ref=f"GRAPH:{clause_id}:deps",
            title=f"Clause relationships for {clause_id}",
            content=body,
        ))
    return out


def _render(row: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))


def retrieve(
    query: str,
    *,
    transaction_id: str | None = None,
    customer_id: str | None = None,
    k: int = DEFAULT_K,
    include_dependencies: bool = True,
) -> GroundingContext:
    tasks = {
        "vector": lambda: _policy(query, k),
        "relational": lambda: _relational(transaction_id),
        "graph": lambda: _graph(transaction_id, customer_id),
    }
    evidence: list[Evidence] = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, future in futures.items():
            try:
                found = future.result()
                evidence.extend(found)
                log.info("retrieval_source", source=name, hits=len(found))
            except Exception as exc:  # noqa: BLE001 - partial grounding beats none
                log.warning("retrieval_source_failed", source=name, error=str(exc))

    # Second hop: let the RECORD decide what else to retrieve. See triggers.py -
    # without this, a fact that exists only in the system of record can never
    # pull its governing clause into context, which is precisely conflict C3.
    fired = triggers.fired(records.get_transaction(transaction_id) if transaction_id else None)
    if fired:
        seen = {e.ref for e in evidence}
        for trigger in fired:
            try:
                for hit in _policy(trigger["query"], max(3, k // 2)):
                    if hit.ref not in seen:
                        seen.add(hit.ref)
                        evidence.append(hit)
            except Exception as exc:  # noqa: BLE001
                log.warning("trigger_retrieval_failed", trigger=trigger["id"], error=str(exc))
        log.info("retrieval_expanded", triggers=[t["id"] for t in fired], total=len(evidence))

    if include_dependencies:
        clause_ids = [e.ref for e in evidence if e.kind == EvidenceKind.POLICY]
        try:
            evidence.extend(_clause_dependencies(clause_ids))
        except Exception as exc:  # noqa: BLE001
            log.warning("clause_dependencies_failed", error=str(exc))

    context = GroundingContext(evidence=evidence)
    log.info("retrieval_complete", total=len(evidence),
             policy=len(context.policy), transaction_id=transaction_id,
             triggers=[t["id"] for t in fired])
    return context
