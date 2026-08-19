"""Mock core-banking HTTP surface (FR-26).

Mounted as a router in the same process - no second daemon, per the zero-Docker
zero-daemon constraint (PRD 7.1). The action workflow calls it over loopback
rather than importing the service functions directly, which is a deliberate
choice: acceptance criterion 6 asks for a 200 from the mock API, and a direct
function call would give a Python object instead. Going over HTTP exercises the
router, the serialisation and the status code - the parts that would actually
break against a real core-banking system.

Everything here is a mock and is labelled as one in its responses. Nothing about
this router should read as a production integration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.tools import core_banking

router = APIRouter(prefix="/api/core-banking", tags=["core-banking (mock)"])


class ProvisionalCreditRequest(BaseModel):
    run_id: str
    amount: float = Field(gt=0)
    account_id: str | None = None
    customer_id: str | None = None
    transaction_id: str | None = None
    currency: str = "USD"
    governing_clause: str = ""
    deadline: str = ""


class DisputeCaseRequest(BaseModel):
    run_id: str
    customer_id: str | None = None
    transaction_id: str | None = None
    reason_code: str = "other"
    queue: str = "disputes"
    amount: float | None = None


class NoticeRequest(BaseModel):
    run_id: str
    customer_id: str | None = None
    subject: str
    body: str
    channel: str = "email"


@router.post("/provisional-credits", status_code=200)
def provisional_credit(req: ProvisionalCreditRequest) -> dict[str, Any]:
    try:
        result = core_banking.issue_provisional_credit(**req.model_dump())
    except core_banking.DuplicateCredit as exc:
        # 409, not 400: the request is well formed and the ledger is refusing
        # it. Same distinction the approval gate draws on a resumed run.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"mock": True, "instrument": "provisional_credit", **result}


@router.post("/dispute-cases", status_code=200)
def dispute_case(req: DisputeCaseRequest) -> dict[str, Any]:
    return {"mock": True, "instrument": "dispute_case",
            **core_banking.open_dispute_case(**req.model_dump())}


@router.post("/notices", status_code=200)
def notice(req: NoticeRequest) -> dict[str, Any]:
    return {"mock": True, "instrument": "customer_notice",
            **core_banking.send_customer_notice(**req.model_dump())}


@router.get("/effects/{run_id}")
def effects(run_id: str) -> dict[str, Any]:
    """What a given run actually did. The rejection path must return three
    empty lists here, which is how criterion 7 is checked rather than claimed."""
    return {"run_id": run_id, **core_banking.effects_for(run_id)}
