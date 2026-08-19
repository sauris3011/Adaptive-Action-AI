"""Graph state.

One TypedDict threaded through every node. Kept flat and JSON-serialisable
because SqliteSaver checkpoints it on every step - a state carrying live client
objects could not survive the interrupt that Stage 4 depends on.

The evidence lives here as a GroundingContext rather than as a rendered string,
so `reconcile` can reason over tiers and `recommend` can cite refs without
re-parsing prose.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from app.schemas.dispute import Attachment, Reconciliation, Recommendation, Triage
from app.schemas.grounding import GroundingContext


def _last(_: Any, new: Any) -> Any:
    """Last write wins. The fan-out writes to distinct keys, so no merge policy
    is needed beyond this."""
    return new


class CopilotState(TypedDict, total=False):
    run_id: str
    started_at: str

    # Input
    request_text: str
    transaction_id: str | None
    customer_id: str | None
    attachments: list[Attachment]

    # Node outputs
    triage: Annotated[Triage | None, _last]
    grounding: Annotated[GroundingContext | None, _last]
    reconciliation: Annotated[Reconciliation | None, _last]
    recommendation: Annotated[Recommendation | None, _last]

    # Trace
    elapsed_ms: int
    error: str | None
