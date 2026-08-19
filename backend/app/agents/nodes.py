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
from app.db import cases, records, trace
from app.graph import extract
from app.llm.factory import invoke_structured
from app.llm.guard import CallClass
from app.logging_setup import get_logger
from app.rag.retrieve import retrieve
from app.schemas.dispute import (
    ActionType,
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


# Actions that assert no dispute exists, so no dispute is recorded for them.
_NON_INTAKE_ACTIONS = (ActionType.ANSWER_ONLY, ActionType.DECLINE)


def open_case_node(state: CopilotState) -> CopilotState:
    """Record the intake against the system of record, before the gate.

    Placed after `recommend` and before `gate` for three reasons. After
    `retrieve`, so the dispute being raised does not turn up in its own
    prior-dispute evidence. Before `gate`, because BDP-2.1 makes intake itself
    the moment a case opens and the amount goes under investigation - no
    monetary instrument is touched here, and every core-banking call stays
    behind the interrupt. Inside the graph rather than in the route handler, so
    the A2A path records intakes on the same terms the UI does.

    A policy question opens nothing: US-5 answers without a case (FR-1).
    """
    triage = state.get("triage")
    recommendation = state.get("recommendation")
    transaction_id = state.get("transaction_id")
    customer_id = state.get("customer_id")

    if triage is None or triage.intent is not Intent.DISPUTE_INTAKE:
        return {}
    if recommendation is None or recommendation.action in _NON_INTAKE_ACTIONS:
        return {}
    if not transaction_id or not customer_id:
        # Nothing to key the record on. Recorded rather than dropped: an intake
        # the copilot could not attach to a transaction is worth seeing.
        trace.record(state["run_id"], "open_case", "skipped", {
            "reason": "no transaction_id or customer_id on the run",
        })
        return {}

    row = records.open_dispute(
        run_id=state["run_id"],
        customer_id=customer_id,
        transaction_id=transaction_id,
        reason_code=triage.reason_code.value,
        amount=recommendation.amount,
    )

    # The relational write is allowed to fail the run - it is the record of
    # truth. The projection is not: a graph that briefly lags SQLite is
    # recoverable by a re-seed, whereas a lost intake is not.
    try:
        extract.project_dispute(row)
        projected = True
    except Exception as exc:  # noqa: BLE001
        log.warning("dispute_projection_failed", run_id=state["run_id"],
                    dispute_id=row["dispute_id"], error=str(exc))
        projected = False

    trace.record(state["run_id"], "open_case", "reused" if row["reused"] else "opened", {
        "dispute_id": row["dispute_id"],
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "reason_code": row["reason_code"],
        "projected_to_graph": projected,
    })
    return {"dispute_id": row["dispute_id"]}


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

    # Close the dispute the intake opened, so the record does not leave a
    # decided case sitting at "open" for the next run to retrieve.
    dispute_id = state.get("dispute_id")
    dispute_outcome = None
    if dispute_id:
        dispute_outcome = records.outcome_for(
            outcome, recommendation.action.value if recommendation else None)
        row = records.set_dispute_outcome(dispute_id=dispute_id, outcome=dispute_outcome,
                                          run_id=state["run_id"])
        if row:
            try:
                extract.project_dispute(row)
            except Exception as exc:  # noqa: BLE001 - see open_case_node
                log.warning("dispute_projection_failed", run_id=state["run_id"],
                            dispute_id=dispute_id, error=str(exc))

    trace.record(state["run_id"], "record", "closed", {
        "case_id": case_id, "outcome": outcome,
        "approver": state.get("approver"),
        "actions": len(results),
        "dispute_id": dispute_id,
        "dispute_outcome": dispute_outcome,
    })
    return {"case_id": case_id}
