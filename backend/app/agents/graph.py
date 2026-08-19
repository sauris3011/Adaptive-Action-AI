"""The LangGraph state machine (PRD 5.1).

    triage -> retrieve -> reconcile -> recommend -> [interrupt]

Linear, with the parallel fan-out inside `retrieve` and the approval interrupt
after `recommend`. A multi-agent crew was considered and rejected in the PRD:
this workflow has no genuinely independent concurrent goals, so role-play agents
would add latency, token cost and failure modes without adding capability.

Durability comes from SqliteSaver on the same database file as everything else,
which is what lets the approval gate survive a page reload - the checkpoint is
on disk, not in memory. Stage 4 resumes from that checkpoint; Stage 3 stops at
it, which is why `recommend` is the interrupt-before target rather than a node
that acts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import reconcile_node, recommend_node, retrieve_node, triage_node
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

    builder.add_edge(START, "triage")
    builder.add_edge("triage", "retrieve")
    builder.add_edge("retrieve", "reconcile")
    builder.add_edge("reconcile", "recommend")
    builder.add_edge("recommend", END)

    _compiled = builder.compile(checkpointer=_saver)
    log.info("graph_compiled", nodes=["triage", "retrieve", "reconcile", "recommend"])
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
    final["elapsed_ms"] = elapsed
    trace.record(run_id, "graph", "awaiting_approval", {"elapsed_ms": elapsed})
    return final


def get_state(run_id: str) -> dict[str, Any] | None:
    """Read a checkpoint back. This is what makes the approval gate survive a
    reload: the UI can recover a run it did not start."""
    graph = build()
    snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
    return dict(snapshot.values) if snapshot and snapshot.values else None
