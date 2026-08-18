"""Grounding enforcement (PRD 5.6).

The master prompt requires grounding on "every LLM call". Applied literally that
injects policy chunks into routing and extraction calls, inflating cost and
latency with no benefit. Intent is read as: NO UNGROUNDED ANSWERS.

Two classes, tagged at the call site:
  GROUNDED - hard-fails on empty context. All answer/recommendation calls.
  UTILITY  - exempt, but the reason is logged on EVERY call, so the exemption
             stays auditable rather than quietly eroding.

This is the only place the rule is enforced. Bypassing it means editing this
file, which is the point.
"""

from __future__ import annotations

from enum import Enum

from app.schemas.grounding import GroundingContext


class CallClass(str, Enum):
    GROUNDED = "grounded"
    UTILITY = "utility"


class UngroundedCallError(RuntimeError):
    """Raised when a GROUNDED call would proceed without evidence."""


def enforce(
    call_class: CallClass,
    grounding: GroundingContext | None,
    *,
    node: str,
    exemption_reason: str | None = None,
) -> str | None:
    """Validate the call. Returns the exemption reason to record on the ledger."""
    if call_class is CallClass.GROUNDED:
        if grounding is None or grounding.is_empty():
            raise UngroundedCallError(
                f"GROUNDED call from node '{node}' has no evidence. Refusing to answer "
                f"from parametric memory. Either supply a GroundingContext or "
                f"reclassify the call as UTILITY with an explicit reason."
            )
        return None

    if not exemption_reason:
        raise ValueError(
            f"UTILITY call from node '{node}' must state an exemption_reason so the "
            f"grounding rule stays auditable."
        )
    return exemption_reason
