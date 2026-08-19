"""Copilot endpoints.

The dispute workflow (US-1, US-5). Stage 3 runs triage -> retrieve -> reconcile
-> recommend and stops with a recommendation awaiting approval; nothing acts on
it yet. The approval gate and the action workflow land in Stage 4, resuming from
the same checkpoint this run leaves behind.

Errors are typed and specific: 409 when a model role is unconfigured, 422 when a
GROUNDED call found no evidence, 502 for an upstream failure. Never a silent
fallback to free text (PRD 5.3).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.agents import actions, graph as agent_graph
from app.db import cases, trace
from app.llm.factory import ModelNotConfigured, SchemaValidationError, invoke_text
from app.llm.guard import CallClass, UngroundedCallError
from app.logging_setup import get_logger
from app.schemas.api import SmokeRequest, SmokeResponse
from app.schemas.dispute import (
    ApprovalRequest,
    ApproverRole,
    DisputeRequest,
    RejectionRequest,
)
from app.tools import core_banking

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
log = get_logger("api.copilot")


@router.post("/smoke", response_model=SmokeResponse)
def smoke(req: SmokeRequest) -> SmokeResponse:
    """Walking-skeleton probe. Moves the header monitor; proves the path works."""
    try:
        reply = invoke_text(
            "triage",
            [HumanMessage(content=req.prompt)],
            call_class=CallClass.UTILITY,
            node="smoke",
            exemption_reason="connectivity probe; answers no user question",
        )
    except ModelNotConfigured as exc:
        # Not an upstream failure: the operator has not chosen a model yet.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # surfaced verbatim - this endpoint exists to diagnose
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SmokeResponse(reply=reply, model_role="triage")


def _serialise(state: dict[str, Any]) -> dict[str, Any]:
    """One shape for both a fresh run and a recovered checkpoint."""
    triage = state.get("triage")
    grounding = state.get("grounding")
    reconciliation = state.get("reconciliation")
    recommendation = state.get("recommendation")

    return {
        "run_id": state.get("run_id"),
        "started_at": state.get("started_at"),
        "elapsed_ms": state.get("elapsed_ms", 0),
        "request_text": state.get("request_text"),
        "transaction_id": state.get("transaction_id"),
        "customer_id": state.get("customer_id"),
        "triage": triage.model_dump(mode="json") if triage else None,
        "evidence": [e.model_dump(mode="json") for e in grounding.by_precedence()]
        if grounding else [],
        "reconciliation": reconciliation.model_dump(mode="json") if reconciliation else None,
        "recommendation": recommendation.model_dump(mode="json") if recommendation else None,
        "decision": state.get("decision"),
        "approver": state.get("approver"),
        "approved_at": state.get("approved_at"),
        "reject_reason": state.get("reject_reason"),
        "case_id": state.get("case_id"),
        # Present from the interrupt onward, unlike case_id which only exists
        # once a decision has been recorded.
        "dispute_id": state.get("dispute_id"),
        "action_results": state.get("action_results") or [],
        # What approving WOULD do, shown before it does it. An approval gate that
        # hides the consequences is a rubber stamp with extra steps.
        "planned_actions": [
            {"instrument": step["instrument"], "payload": step["payload"]}
            for step in (actions.plan(recommendation, state) if recommendation else [])
        ],
        "status": _status(state, recommendation),
    }


def _status(state: dict[str, Any], recommendation: Any) -> str:
    if state.get("decision") == "rejected":
        return "rejected"
    if state.get("decision") == "approved":
        results = state.get("action_results") or []
        if any(r.get("status_code") != 200 for r in results):
            return "approved_action_failed"
        return "approved"
    if recommendation:
        return "awaiting_approval"
    return "incomplete"


@router.post("/disputes")
def submit_dispute(req: DisputeRequest) -> dict[str, Any]:
    """US-1 and US-5. Returns a grounded, cited recommendation awaiting approval."""
    try:
        final = agent_graph.run(
            req.text,
            transaction_id=req.transaction_id,
            customer_id=req.customer_id,
            attachments=req.attachments,
        )
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UngroundedCallError as exc:
        # The guard did its job (acceptance criterion 10). 422, not 500: the
        # request was well formed, the corpus had nothing to say about it.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SchemaValidationError as exc:
        # A typed error, surfaced as itself. The alternative PRD 5.3 forbids is
        # quietly returning whatever free text the model produced.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _serialise(final)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Recover a run from its checkpoint - what makes the gate survive a reload."""
    state = agent_graph.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"no run '{run_id}'")
    return _serialise(state) | {
        "events": trace.events(run_id),
        "awaiting_approval": agent_graph.is_awaiting_approval(run_id),
        "effects": core_banking.effects_for(run_id),
        "case": cases.by_run(run_id),
    }


@router.get("/runs")
def list_runs(limit: int = 25) -> dict[str, Any]:
    return {"runs": trace.runs(limit)}


AGENT_AUTHORITY_LIMIT = 500.0


def _load_or_404(run_id: str) -> dict[str, Any]:
    state = agent_graph.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"no run '{run_id}'")
    return state


def _resume_or_error(run_id: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return agent_graph.resume(run_id, **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"no run '{run_id}'") from exc
    except agent_graph.NotAwaitingApproval as exc:
        # 409, not 400: the request is valid, the run has simply moved on. This
        # is also what makes a double-clicked Approve harmless.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/approve")
def approve(run_id: str, req: ApprovalRequest) -> dict[str, Any]:
    """FR-7. The only route from a recommendation to a monetary action."""
    state = _load_or_404(run_id)
    recommendation = state.get("recommendation")
    if recommendation is None:
        raise HTTPException(status_code=409, detail="run has no recommendation to approve")

    # BDP-3.4, enforced in code rather than trusted to the reviewer's memory.
    # This is a policy limit, NOT authentication: the operator asserts their own
    # role and nothing verifies it (PRD section 8 excludes auth and RBAC).
    amount = recommendation.amount or 0.0
    if amount > AGENT_AUTHORITY_LIMIT and req.approver_role is not ApproverRole.TEAM_LEAD:
        raise HTTPException(
            status_code=403,
            detail=(
                f"BDP-3.4: provisional credit above {AGENT_AUTHORITY_LIMIT:.0f} USD requires "
                f"Disputes Team Lead approval; this run is for {amount:.2f} USD and the "
                f"approver is recorded as '{req.approver_role.value}'."
            ),
        )

    final = _resume_or_error(
        run_id, decision="approved", approver=req.approver,
        approver_role=req.approver_role.value, note=req.note,
    )
    return _serialise(final) | {
        "effects": core_banking.effects_for(run_id),
        "case": cases.by_run(run_id),
    }


@router.post("/runs/{run_id}/reject")
def reject(run_id: str, req: RejectionRequest) -> dict[str, Any]:
    """FR-8. No side effect on the mock API; the outcome is still recorded."""
    _load_or_404(run_id)
    final = _resume_or_error(
        run_id, decision="rejected", approver=req.approver, reject_reason=req.reason,
    )
    return _serialise(final) | {
        # Returned so the caller can VERIFY the absence of effects rather than
        # take it on trust (acceptance criterion 7).
        "effects": core_banking.effects_for(run_id),
        "case": cases.by_run(run_id),
    }


@router.post("/cases/{case_id}/evidence")
def attach_evidence(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach a graph answer to a case as evidence (US-4).

    Written into the same run_events trace the agent writes to, not a side
    table: evidence an operator added by hand and evidence the pipeline
    retrieved have to be equally auditable, and a reviewer should not have to
    know which of the two they are looking at to find it.
    """
    case = cases.by_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"no case '{case_id}'")

    trace.record(
        case["run_id"],
        node="graph_search",
        event="evidence_attached",
        payload={
            "case_id": case_id,
            "resolved_call": payload.get("resolved_call"),
            "method": payload.get("method"),
            "entity": payload.get("entity"),
            "answer": payload.get("answer"),
            "backend": payload.get("backend"),
        },
    )
    log.info("graph_evidence_attached", case_id=case_id, run_id=case["run_id"],
             method=payload.get("method"))
    return {"case_id": case_id, "run_id": case["run_id"], "attached": True}


@router.get("/cases")
def list_cases(limit: int = 50) -> dict[str, Any]:
    """The audit view (US-4): every decision, its approver and its outcome."""
    return {"cases": cases.recent(limit), "by_outcome": cases.counts_by_outcome()}
