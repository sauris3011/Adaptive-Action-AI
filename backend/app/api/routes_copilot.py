"""Copilot endpoints.

Stage 1 ships only the smoke probe, which exercises the entire LLM path -
gateway, TLS policy, retries, guard, ledger - so the walking skeleton is
verifiable before any agent logic exists. The dispute workflow lands here in
Stage 3.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.llm.factory import ModelNotConfigured, invoke_text
from app.llm.guard import CallClass
from app.schemas.api import SmokeRequest, SmokeResponse

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


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
