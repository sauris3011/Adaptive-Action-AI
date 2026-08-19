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

from app.agents import graph as agent_graph
from app.db import trace
from app.llm.factory import ModelNotConfigured, invoke_text
from app.llm.guard import CallClass, UngroundedCallError
from app.logging_setup import get_logger
from app.schemas.api import SmokeRequest, SmokeResponse
from app.schemas.dispute import DisputeRequest

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
        # Stage 3 always ends here. Stage 4 replaces this with the real gate.
        "status": "awaiting_approval" if recommendation else "incomplete",
    }


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
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _serialise(final)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Recover a run from its checkpoint - what makes the gate survive a reload."""
    state = agent_graph.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"no run '{run_id}'")
    return _serialise(state) | {"events": trace.events(run_id)}


@router.get("/runs")
def list_runs(limit: int = 25) -> dict[str, Any]:
    return {"runs": trace.runs(limit)}
