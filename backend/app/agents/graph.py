"""The LangGraph state machine (PRD 5.1).

    triage -> retrieve -> reconcile -> recommend -> [INTERRUPT] -> gate
                                                                     |
                                                    approve -> act -> record
                                                    reject  ---------> record

Linear, with the parallel fan-out inside `retrieve` and one interrupt before
`gate`. A multi-agent crew was considered and rejected in the PRD: this workflow
has no genuinely independent concurrent goals, so role-play agents would add
latency, token cost and failure modes without adding capability.

The interrupt sits BEFORE `gate` rather than inside it, so the pause happens
with the recommendation complete and no node yet running that could act. There
is no code path from `recommend` to `act` that does not pass through a human
decision written into the checkpoint (FR-6).

Durability comes from SqliteSaver on the same database file as everything else,
which is what lets the approval gate survive a page reload - the checkpoint is
on disk, not in memory.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    act_node,
    gate_node,
    reconcile_node,
    recommend_node,
    record_node,
    retrieve_node,
    route_decision,
    triage_node,
)
from app.agents.state import CopilotState
from app.config import get_settings
from app.db import trace
from app.logging_setup import get_logger
from app.schemas.dispute import Attachment

log = get_logger("agents.graph")

_compiled: Any | None = None
_saver: SqliteSaver | None = None


def build() -> Any:
    """Compile once. The topology is static; only the state changes per run."""
    global _compiled, _saver
    if _compiled is not None:
        return _compiled

    settings = get_settings()
    settings.ensure_dirs()

    import sqlite3

    # check_same_thread=False because FastAPI dispatches handlers across threads
    # and the saver outlives any one of them. Writes are serialised by SQLite.
    connection = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    _saver = SqliteSaver(connection)

    builder = StateGraph(CopilotState)
    builder.add_node("triage", triage_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("reconcile", reconcile_node)
    builder.add_node("recommend", recommend_node)
    builder.add_node("gate", gate_node)
    builder.add_node("act", act_node)
    builder.add_node("record", record_node)

    builder.add_edge(START, "triage")
    builder.add_edge("triage", "retrieve")
    builder.add_edge("retrieve", "reconcile")
    builder.add_edge("reconcile", "recommend")
    builder.add_edge("recommend", "gate")
    builder.add_conditional_edges("gate", route_decision,
                                  {"act": "act", "record": "record"})
    builder.add_edge("act", "record")
    builder.add_edge("record", END)

    # The whole approval guarantee rests on this one argument.
    _compiled = builder.compile(checkpointer=_saver, interrupt_before=["gate"])
    log.info("graph_compiled",
             nodes=["triage", "retrieve", "reconcile", "recommend", "gate", "act", "record"],
             interrupt_before=["gate"])
    return _compiled


def run(
    text: str,
    *,
    transaction_id: str | None = None,
    customer_id: str | None = None,
    attachments: list[Attachment] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute one pass. Returns the final state."""
    graph = build()
    run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    started = datetime.now(timezone.utc)

    initial: CopilotState = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "request_text": text,
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "attachments": attachments or [],
    }
    trace.record(run_id, "graph", "started", {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "attachments": [a.filename for a in attachments or []],
    })

    config = {"configurable": {"thread_id": run_id}}
    try:
        final = graph.invoke(initial, config=config)
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed error, never a silent fallback
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        trace.record(run_id, "graph", "failed", {"error": str(exc), "elapsed_ms": elapsed})
        log.error("run_failed", run_id=run_id, error=str(exc))
        raise

    elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    # The invoke returned because it hit the interrupt, not because it finished.
    # Persist the elapsed time into the checkpoint so a recovered run reports the
    # same latency the operator originally saw.
    graph.update_state(config, {"elapsed_ms": elapsed})
    final["elapsed_ms"] = elapsed
    trace.record(run_id, "graph", "awaiting_approval", {"elapsed_ms": elapsed})
    return final


def get_state(run_id: str) -> dict[str, Any] | None:
    """Read a checkpoint back. This is what makes the approval gate survive a
    reload: the UI can recover a run it did not start."""
    graph = build()
    snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
    return dict(snapshot.values) if snapshot and snapshot.values else None


class NotAwaitingApproval(RuntimeError):
    """Resume attempted on a run that is not paused at the gate."""


def is_awaiting_approval(run_id: str) -> bool:
    """True only when the checkpoint is parked at the interrupt.

    Read from LangGraph's own `next` rather than from a status column we
    maintain: a duplicated status field would eventually disagree with the
    checkpoint, and the checkpoint is what actually governs execution.
    """
    graph = build()
    snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
    return bool(snapshot and snapshot.next and "gate" in snapshot.next)


def resume(
    run_id: str,
    *,
    decision: str,
    approver: str,
    approver_role: str | None = None,
    note: str = "",
    reject_reason: str | None = None,
) -> dict[str, Any]:
    """Write the human decision into the checkpoint, then let the graph continue.

    This is the ONLY way execution proceeds past `recommend`. The decision is
    persisted before the graph runs, so an approval that crashes mid-action is
    still attributable to whoever gave it.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"decision must be 'approved' or 'rejected', got '{decision}'")

    graph = build()
    config = {"configurable": {"thread_id": run_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise KeyError(run_id)
    if not (snapshot.next and "gate" in snapshot.next):
        raise NotAwaitingApproval(
            f"run '{run_id}' is not awaiting approval (next={snapshot.next or 'done'}). "
            f"A decision has already been recorded for it."
        )

    decided_at = datetime.now(timezone.utc).isoformat()
    graph.update_state(config, {
        "decision": decision,
        "approver": approver,
        "approver_role": approver_role,
        "approval_note": note,
        "reject_reason": reject_reason,
        "approved_at": decided_at,
    })
    trace.record(run_id, "gate", decision, {
        "approver": approver, "approver_role": approver_role,
        "reason": reject_reason, "note": note, "at": decided_at,
    })

    # Resuming with None continues from the checkpoint rather than restarting.
    return graph.invoke(None, config=config)
