"""Structured output contracts for the reasoning pipeline (PRD 5.3).

Every LLM response that enters application logic is one of these models,
requested via LangChain's structured-output binding and validated before use.
There is no free-text path into the workflow.

Field descriptions are load-bearing: they are what the model actually sees when
the schema is bound, so they carry the instruction, not just the documentation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.schemas.grounding import SourceTier


class ReasonCode(str, Enum):
    UNAUTHORISED = "unauthorised"
    GOODS_NOT_RECEIVED = "goods_not_received"
    DUPLICATE_CHARGE = "duplicate_charge"
    INCORRECT_AMOUNT = "incorrect_amount"
    CANCELLED_RECURRING = "cancelled_recurring"
    QUALITY_DISPUTE = "quality_dispute"
    OTHER = "other"


class Intent(str, Enum):
    """US-1 opens a case; US-5 answers a question without opening one."""

    DISPUTE_INTAKE = "dispute_intake"
    POLICY_QUESTION = "policy_question"


class Attachment(BaseModel):
    """PRD 8.1 provision 4: carried from day one.

    Non-text attachments are accepted, stored and surfaced in the trace. They
    are not yet interpreted, and the recommendation must not pretend otherwise.
    """

    filename: str
    modality: str = "text"
    source_uri: str | None = None


class DisputeRequest(BaseModel):
    """What the agent submits from the UI."""

    text: str = Field(min_length=4, max_length=4000)
    transaction_id: str | None = None
    customer_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class Triage(BaseModel):
    """Extraction output (FR-1). Entities are hints, never authority.

    Anything the model extracts here is re-read from the system of record before
    it is relied on - an LLM-parsed transaction id is a lookup key, not a fact.
    """

    intent: Intent = Field(description="dispute_intake if the user wants a case opened or a "
                                       "decision made; policy_question if they only want an answer")
    transaction_id: str | None = Field(default=None, description="Transaction id if stated, e.g. TXN-9001")
    customer_id: str | None = Field(default=None, description="Customer id if stated, e.g. CUST-1001")
    merchant_hint: str | None = Field(default=None, description="Merchant name if stated")
    amount: float | None = Field(default=None, description="Disputed amount if stated")
    reason_code: ReasonCode = Field(description="Closest matching dispute reason")
    summary: str = Field(max_length=400, description="One sentence restating the request")
    retrieval_query: str = Field(
        max_length=300,
        description="A focused query for policy retrieval. State the substantive question, "
                    "not the customer's narrative.",
    )


class Conflict(BaseModel):
    """One detected contradiction (FR-3, FR-16).

    `is_true_conflict` exists because C2 is the case where two clauses appear to
    disagree but govern different instruments. Collapsing that into "conflict"
    would make the copilot confidently wrong in exactly the way the product
    thesis says conventional RAG is.
    """

    description: str = Field(max_length=600, description="What the sources disagree about")
    governing_clause: str = Field(description="Clause id that governs, e.g. PCT-7.1")
    governing_tier: SourceTier = Field(description="Precedence tier of the governing clause")
    superseded_clauses: list[str] = Field(
        default_factory=list, description="Clause ids that do NOT govern here")
    is_true_conflict: bool = Field(
        description="False when the clauses govern different instruments or scopes and only "
                    "appear to disagree")
    resolution_basis: str = Field(
        max_length=600,
        description="Why the governing clause wins: which precedence rule applied, or why the "
                    "conflict is only apparent",
    )


class Reconciliation(BaseModel):
    """`reconcile` output. Empty conflicts is a valid, meaningful answer."""

    conflicts: list[Conflict] = Field(default_factory=list)
    notes: str = Field(default="", max_length=800,
                       description="Anything material the conflicts list does not capture")


class ActionType(str, Enum):
    PROVISIONAL_CREDIT = "provisional_credit"
    GOODWILL_REFUND = "goodwill_refund"
    ROUTE_TO_FRAUD_OPS = "route_to_fraud_ops"
    REQUEST_MERCHANT_CONTACT = "request_merchant_contact"
    DECLINE = "decline"
    ANSWER_ONLY = "answer_only"


class Recommendation(BaseModel):
    """FR-4 and FR-5. At least one citation is enforced, not requested."""

    action: ActionType
    headline: str = Field(max_length=200, description="The recommendation in one line")
    rationale: str = Field(max_length=2000, description="Why, referencing clause ids inline")
    citations: list[str] = Field(
        min_length=1,
        description="Clause ids and record refs this rests on, e.g. ['PCT-7.1', 'REC:TXN-9002']",
    )
    governing_clause: str = Field(description="The single clause that decides the outcome")
    deadline: str = Field(
        max_length=200,
        description="The applicable deadline stated concretely, e.g. '2 business days from "
                    "notice'. State 'none applicable' only when genuinely none applies.",
    )
    amount: float | None = Field(default=None, description="Monetary amount if the action has one")
    requires_approval: bool = Field(
        description="True for any action moving money or opening a case")
    confidence: float = Field(ge=0.0, le=1.0,
                              description="0-1. Lower it when evidence is thin or conflicting.")
    caveats: str = Field(default="", max_length=800,
                         description="What a reviewer should check before approving")

    @field_validator("citations")
    @classmethod
    def _no_blank_citations(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c and c.strip()]
        if not cleaned:
            raise ValueError(
                "at least one citation is required (FR-5); a recommendation without a "
                "governing clause is not a recommendation"
            )
        return cleaned
