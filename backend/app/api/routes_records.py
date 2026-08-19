"""Authoritative-record endpoints behind the transaction look-up screen.

Separate from `routes_grounding` on purpose: the look-up is the *relational*
grounding source on its own terms - one field over the system of record, with
the routing signals the model never gets to author.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import lookup

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("/transactions")
def transactions(
    q: str = Query(default="", description="Reference, merchant, amount or card tail"),
    scope: Literal["30d", "90d", "all"] = Query(default="30d"),
) -> dict[str, Any]:
    """Filter live as the operator types - there is no submit on this screen.

    Filtering server-side rather than shipping the table and slicing it in the
    browser keeps the same query shape when the record grows past a fixture, and
    keeps the duplicate rule in one place.
    """
    return lookup.search(q=q, scope=scope)


@router.get("/transactions/{transaction_id}")
def transaction(transaction_id: str) -> dict[str, Any]:
    """The detail rail's row, refetched by id so a deep link works."""
    row = lookup.get(transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no transaction '{transaction_id}'")
    return row
