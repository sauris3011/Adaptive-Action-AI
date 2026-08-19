"""A2A conformance slice (FR-25).

A SLICE, and described as one everywhere it is visible: an agent card plus a
single JSON-RPC method. PRD section 8 explicitly excludes full A2A - no
discovery, no authentication, no cross-boundary negotiation - and the agent card
says so in its own `description` rather than implying conformance it does not
have. Overclaiming here would be the easiest thing in the build to get away with
and the least honest.

`message/send` runs the same graph the UI does and stops at the same approval
gate. An agent calling in cannot execute a monetary action, because there is no
path that skips the human decision (FR-6) - the interrupt is a property of the
graph, not of the HTTP layer in front of it.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents import graph as agent_graph
from app.config import get_settings
from app.llm.factory import ModelNotConfigured, SchemaValidationError
from app.llm.guard import UngroundedCallError
from app.logging_setup import get_logger

log = get_logger("api.a2a")
router = APIRouter(tags=["a2a"])

PROTOCOL_VERSION = "0.2.0"

# JSON-RPC 2.0 reserved codes, plus one application code.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND = -32700, -32600, -32601
INVALID_PARAMS, INTERNAL_ERROR, AGENT_ERROR = -32602, -32603, -32000


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


@router.get("/.well-known/agent.json")
def agent_card() -> dict[str, Any]:
    """The discovery document. Served unauthenticated by design - it advertises
    capability, and everything it advertises is already reachable."""
    settings = get_settings()
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "name": "Adaptive Knowledge-to-Action Copilot",
        "description": (
            "Grounds a work request in policy documents, a knowledge graph and systems "
            "of record, reconciles contradictory sources under a declared precedence "
            "order, and returns a cited recommendation held at a human approval gate. "
            "This endpoint implements a CONFORMANCE SLICE of A2A: an agent card and the "
            "message/send method only. Discovery, authentication and cross-boundary "
            "negotiation are out of scope."
        ),
        "url": f"http://{settings.host}:{settings.port}/a2a",
        "version": "0.1.0",
        "provider": {"organization": "Adaptive Action AI (prototype)"},
        "capabilities": {"streaming": False, "pushNotifications": False,
                         "stateTransitionHistory": True},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "dispute-recommendation",
                "name": "Card dispute recommendation",
                "description": (
                    "Returns a grounded recommendation for a card transaction dispute, "
                    "with the governing clause, citations, applicable deadline and any "
                    "detected conflict between sources. Never executes a monetary "
                    "action: the run halts at a human approval gate."
                ),
                "tags": ["banking", "disputes", "reconciliation", "rag", "graphrag"],
                "examples": [
                    "Cardholder disputes a 420 USD charge she says she did not authorise; "
                    "transaction TXN-9001.",
                    "When must a Signature cardholder receive provisional credit?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            }
        ],
        "methods": ["message/send"],
        "limitations": [
            "Conformance slice only: no task lifecycle, streaming, or push notifications.",
            "No authentication. Intended for local prototype use on synthetic data.",
            "Cannot execute an action. Approval is a human decision made outside this API.",
        ],
    }


def _extract_text(params: dict[str, Any]) -> str:
    """Accept the A2A message shape, and a bare `text` for convenience.

    Being liberal here costs nothing and makes the endpoint testable with curl
    without hand-assembling a parts array.
    """
    message = params.get("message") or {}
    parts = message.get("parts") or []
    texts = [p.get("text", "") for p in parts if p.get("kind", "text") == "text"]
    joined = "\n".join(t for t in texts if t).strip()
    return joined or str(params.get("text") or "").strip()


@router.post("/a2a")
def json_rpc(request: JsonRpcRequest) -> dict[str, Any]:
    if request.method != "message/send":
        return _error(request.id, METHOD_NOT_FOUND,
                      f"unsupported method '{request.method}'",
                      {"supported": ["message/send"]})

    text = _extract_text(request.params)
    if len(text) < 4:
        return _error(request.id, INVALID_PARAMS,
                      "params.message.parts must contain text of at least 4 characters")

    metadata = request.params.get("metadata") or {}
    try:
        state = agent_graph.run(
            text,
            transaction_id=metadata.get("transaction_id"),
            customer_id=metadata.get("customer_id"),
        )
    except ModelNotConfigured as exc:
        return _error(request.id, AGENT_ERROR, "no model configured for a required role",
                      {"detail": str(exc)})
    except (UngroundedCallError, SchemaValidationError) as exc:
        return _error(request.id, AGENT_ERROR, "agent could not produce a grounded answer",
                      {"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        log.error("a2a_run_failed", error=str(exc))
        return _error(request.id, INTERNAL_ERROR, "agent run failed", {"detail": str(exc)})

    recommendation = state.get("recommendation")
    reconciliation = state.get("reconciliation")
    grounding = state.get("grounding")

    return _result(request.id, {
        "taskId": state.get("run_id"),
        # "input-required" is the A2A state for work halted pending a human. It
        # is the honest description of an approval gate.
        "status": {"state": "input-required",
                   "message": "Recommendation ready and awaiting human approval. "
                              "No action has been executed."},
        "artifacts": [{
            "name": "recommendation",
            "parts": [{"kind": "data", "data": recommendation.model_dump(mode="json")}],
        }] if recommendation else [],
        "reconciliation": reconciliation.model_dump(mode="json") if reconciliation else None,
        "citations": grounding.citations() if grounding else [],
        "elapsedMs": state.get("elapsed_ms", 0),
    })
