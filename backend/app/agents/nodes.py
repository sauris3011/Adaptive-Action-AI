"""The graph's nodes (PRD 5.1).

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

from app.agents import actions, prompts
from app.agents.state import CopilotState
from app.db import cases, trace
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


# --------------------------------------------------------------------------
# Stage 4: approval gate, action workflow, outcome recording
# --------------------------------------------------------------------------

def gate_node(state: CopilotState) -> CopilotState:
    """The interrupt target (FR-6).

    Deliberately does nothing. The graph is compiled with
    interrupt_before=["gate"], so execution stops here with the recommendation
    complete and NOTHING executed. The decision arrives later via update_state,
    and this node exists only to give the resume a place to land and the routing
    a place to branch from.

    Keeping it empty matters: the moment this node makes a decision, the human
    gate becomes advisory.
    """
    decision = state.get("decision")
    trace.record(state["run_id"], "gate", "resumed", {
        "decision": decision,
        "approver": state.get("approver"),
        "approver_role": state.get("approver_role"),
    })
    return {}


def route_decision(state: CopilotState) -> str:
    """approve -> act, reject -> record. An absent decision is a bug, not a
    default: resuming without one would be a silent auto-approval."""
    decision = state.get("decision")
    if decision == "approved":
        return "act"
    if decision == "rejected":
        return "record"
    raise RuntimeError(
        f"run '{state.get('run_id')}' resumed with no decision. Refusing to route: "
        f"an unset decision must never fall through to the action path."
    )


def act_node(state: CopilotState) -> CopilotState:
    """FR-7. Executes only on the approved branch, only after the interrupt."""
    started = time.perf_counter()
    recommendation = state.get("recommendation")
    if recommendation is None:
        raise RuntimeError("act reached with no recommendation")

    results = actions.execute(recommendation, dict(state))
    failed = [r for r in results if r["status_code"] != 200]

    trace.record(state["run_id"], "act", "executed", {
        "steps": len(results),
        "instruments": [r["instrument"] for r in results],
        "references": [r["reference"] for r in results],
        "failed": len(failed),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    })
    return {"action_results": results}


def record_node(state: CopilotState) -> CopilotState:
    """FR-8 and FR-9. Runs on BOTH branches.

    A rejection performs no side effect but is still recorded - "no trace" and
    "no effect" are different things, and only the second one is required.
    """
    recommendation = state.get("recommendation")
    triage = state.get("triage")
    decision = state.get("decision")
    results = state.get("action_results") or []

    case_id = f"CASE-{state['run_id'].removeprefix('run-').upper()}"
    outcome = decision or "unresolved"
    if decision == "approved" and any(r["status_code"] != 200 for r in results):
        # An approved run whose actions failed is neither "approved" nor
        # "rejected" for reporting purposes, and must not be counted as resolved.
        outcome = "approved_action_failed"

    cases.upsert(
        case_id=case_id,
        run_id=state["run_id"],
        customer_id=state.get("customer_id"),
        transaction_id=state.get("transaction_id"),
        reason_code=triage.reason_code.value if triage else None,
        recommendation=recommendation.action.value if recommendation else "",
        governing_clause=recommendation.governing_clause if recommendation else "",
        confidence=recommendation.confidence if recommendation else None,
        outcome=outcome,
        approver=state.get("approver"),
        approved_at=state.get("approved_at"),
        reject_reason=state.get("reject_reason"),
        elapsed_ms=state.get("elapsed_ms"),
    )

    trace.record(state["run_id"], "record", "closed", {
        "case_id": case_id, "outcome": outcome,
        "approver": state.get("approver"),
        "actions": len(results),
    })
    return {"case_id": case_id}
