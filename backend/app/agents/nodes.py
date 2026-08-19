"""The four reasoning nodes (PRD 5.1).

Model roles follow PRD 5.2: `triage` on the cheap tier, `reason` on the strongest
available for reconcile and recommend - the only two steps doing genuine
multi-source reasoning.

Call classes follow PRD 5.6. `triage` is UTILITY with a logged reason: it
extracts fields from the user's own text and answers nothing. `reconcile` and
`recommend` are GROUNDED and will refuse to run on empty evidence.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents import prompts
from app.agents.state import CopilotState
from app.db import trace
from app.llm.factory import invoke_structured
from app.llm.guard import CallClass
from app.logging_setup import get_logger
from app.rag.retrieve import retrieve
from app.schemas.dispute import (
    Intent,
    Reconciliation,
    Recommendation,
    Triage,
)

log = get_logger("agents.nodes")


def triage_node(state: CopilotState) -> CopilotState:
    """FR-1. Extract intent and entities into a validated schema."""
    started = time.perf_counter()
    result = invoke_structured(
        "triage",
        [SystemMessage(content=prompts.TRIAGE_SYSTEM),
         HumanMessage(content=prompts.triage_user(state["request_text"]))],
        Triage,
        call_class=CallClass.UTILITY,
        node="triage",
        exemption_reason="extraction over the user's own text; produces no answer or "
                         "recommendation and asserts nothing about policy",
        run_id=state.get("run_id"),
    )

    # Explicit ids from the caller outrank anything the model extracted: the UI
    # knows which record it is looking at, the model is guessing from prose.
    transaction_id = state.get("transaction_id") or result.transaction_id
    customer_id = state.get("customer_id") or result.customer_id

    trace.record(state["run_id"], "triage", "extracted", {
        "intent": result.intent.value,
        "reason_code": result.reason_code.value,
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "retrieval_query": result.retrieval_query,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    })
    return {"triage": result, "transaction_id": transaction_id, "customer_id": customer_id}


def retrieve_node(state: CopilotState) -> CopilotState:
    """FR-2. The parallel fan-out itself lives in rag.retrieve.

    The fan-out is threads inside one node rather than three LangGraph branches:
    the sources are pure reads with no independent control flow, so three
    checkpointed branches would buy nothing and cost three checkpoint writes.
    """
    started = time.perf_counter()
    triage = state.get("triage")
    query = triage.retrieval_query if triage else state["request_text"]

    context = retrieve(
        query,
        transaction_id=state.get("transaction_id"),
        customer_id=state.get("customer_id"),
    )

    trace.record(state["run_id"], "retrieve", "grounded", {
        "query": query,
        "evidence": len(context.evidence),
        "policy": len(context.policy),
        "refs": context.citations(),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    })
    return {"grounding": context}


def reconcile_node(state: CopilotState) -> CopilotState:
    """FR-3. The product thesis (PRD 1.4) in one node."""
    started = time.perf_counter()
    grounding = state.get("grounding")
    triage = state.get("triage")
    question = triage.retrieval_query if triage else state["request_text"]

    result = invoke_structured(
        "reason",
        [SystemMessage(content=prompts.RECONCILE_SYSTEM),
         HumanMessage(content=prompts.reconcile_user(question, grounding))],
        Reconciliation,
        call_class=CallClass.GROUNDED,
        node="reconcile",
        grounding=grounding,
        run_id=state.get("run_id"),
    )

    trace.record(state["run_id"], "reconcile", "resolved", {
        "conflicts": len(result.conflicts),
        "true_conflicts": sum(1 for c in result.conflicts if c.is_true_conflict),
        "governing": [c.governing_clause for c in result.conflicts],
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    })
    return {"reconciliation": result}


def recommend_node(state: CopilotState) -> CopilotState:
    """FR-4 and FR-5. Citation count is enforced by the schema, not the prompt."""
    started = time.perf_counter()
    grounding = state.get("grounding")
    triage = state.get("triage")
    reconciliation = state.get("reconciliation")

    is_question = triage is not None and triage.intent is Intent.POLICY_QUESTION
    system = prompts.QA_SYSTEM if is_question else prompts.RECOMMEND_SYSTEM
    summary = prompts.render_reconciliation(
        reconciliation.conflicts if reconciliation else [],
        reconciliation.notes if reconciliation else "",
    )

    result = invoke_structured(
        "reason",
        [SystemMessage(content=system),
         HumanMessage(content=prompts.recommend_user(
             state["request_text"], grounding, summary,
             [a.filename for a in state.get("attachments", [])],
         ))],
        Recommendation,
        call_class=CallClass.GROUNDED,
        node="recommend",
        grounding=grounding,
        run_id=state.get("run_id"),
    )

    known = set(grounding.citations()) if grounding else set()
    unknown = [c for c in result.citations if c not in known]
    if unknown:
        # Not fatal, but it is exactly the failure FR-5 exists to catch, so it is
        # logged and surfaced in the trace rather than quietly accepted.
        log.warning("citation_not_in_evidence", run_id=state.get("run_id"), refs=unknown)

    trace.record(state["run_id"], "recommend", "produced", {
        "action": result.action.value,
        "governing_clause": result.governing_clause,
        "citations": result.citations,
        "unverified_citations": unknown,
        "confidence": result.confidence,
        "requires_approval": result.requires_approval,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    })
    return {"recommendation": result}
