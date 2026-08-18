"""Grounding primitives.

Evidence is a TYPED item, not a string (PRD 8.1 provision 3). That is what lets
image or table evidence join the context later without touching the guard or
prompt assembly.
"""

from __future__ import annotations

from enum import Enum, IntEnum

from pydantic import BaseModel, Field


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"   # reserved - accepted and stored, not yet interpreted
    TABLE = "table"   # reserved


class SourceTier(IntEnum):
    """Precedence ladder (PRD 5.4). Lower value wins.

    Assigned at ingestion, so precedence is a deterministic property of the
    corpus rather than an LLM judgement call. The model identifies a
    contradiction; this ladder resolves it.
    """

    REGULATION = 1
    NETWORK_RULES = 2
    BANK_POLICY = 3
    PRODUCT_TERMS = 4

    @property
    def label(self) -> str:
        return {
            SourceTier.REGULATION: "Regulatory requirement",
            SourceTier.NETWORK_RULES: "Card network rules",
            SourceTier.BANK_POLICY: "Bank policy & SOP",
            SourceTier.PRODUCT_TERMS: "Product terms & conditions",
        }[self]


class EvidenceKind(str, Enum):
    POLICY = "policy"   # vector hit over the document corpus
    GRAPH = "graph"     # entity/relationship from the knowledge graph
    RECORD = "record"   # authoritative fact from the relational store


class Evidence(BaseModel):
    kind: EvidenceKind
    ref: str = Field(description="Clause ID, node ID or record key - the citation handle")
    title: str = ""
    content: str
    modality: Modality = Modality.TEXT
    tier: SourceTier | None = None
    source_uri: str | None = None
    score: float | None = None

    def render(self) -> str:
        tier = f" | tier: {self.tier.label}" if self.tier is not None else ""
        return f"[{self.ref}] {self.title}{tier}\n{self.content}".strip()


class GroundingContext(BaseModel):
    """Mandatory input to every GROUNDED call (PRD 5.6)."""

    evidence: list[Evidence] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.evidence

    @property
    def policy(self) -> list[Evidence]:
        return [e for e in self.evidence if e.kind == EvidenceKind.POLICY]

    def by_precedence(self) -> list[Evidence]:
        """Highest-precedence first; untiered evidence sorts last."""
        return sorted(
            self.evidence,
            key=lambda e: (e.tier.value if e.tier is not None else 99, e.ref),
        )

    def render(self) -> str:
        if self.is_empty():
            return ""
        blocks = [e.render() for e in self.by_precedence()]
        return "\n\n---\n\n".join(blocks)

    def citations(self) -> list[str]:
        return [e.ref for e in self.evidence]
