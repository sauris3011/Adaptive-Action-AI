"""Document and chunk models for the ingestion path.

Every Document and Chunk carries `modality` and `source_uri` from day one
(PRD 8.1 provision 2), so a binary asset can be referenced later without a
schema migration. Only `text` is interpreted today.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.grounding import Evidence, EvidenceKind, Modality, SourceTier


class Document(BaseModel):
    doc_id: str
    title: str
    tier: SourceTier
    modality: Modality = Modality.TEXT
    source_uri: str
    authority: str = ""
    effective: str = ""
    text: str = ""
    meta: dict[str, str] = Field(default_factory=dict)
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Chunk(BaseModel):
    """One clause. The clause IS the chunk boundary, which is what makes
    `clause_id` a reliable citation handle rather than a best guess."""

    chunk_id: str
    doc_id: str
    clause_id: str
    title: str
    tier: SourceTier
    modality: Modality = Modality.TEXT
    source_uri: str
    text: str
    ordinal: int = 0

    @staticmethod
    def make_id(doc_id: str, clause_id: str, text: str) -> str:
        digest = hashlib.sha256(f"{doc_id}|{clause_id}|{text}".encode()).hexdigest()[:12]
        return f"{clause_id}#{digest}"

    def to_evidence(self, score: float | None = None) -> Evidence:
        return Evidence(
            kind=EvidenceKind.POLICY,
            ref=self.clause_id,
            title=self.title,
            content=self.text,
            modality=self.modality,
            tier=self.tier,
            source_uri=self.source_uri,
            score=score,
        )

    def metadata(self) -> dict[str, str | int]:
        """Chroma metadata. Scalars only - Chroma rejects nested values."""
        return {
            "doc_id": self.doc_id,
            "clause_id": self.clause_id,
            "title": self.title,
            "tier": int(self.tier),
            "tier_label": self.tier.label,
            "modality": self.modality.value,
            "source_uri": self.source_uri,
            "ordinal": self.ordinal,
        }
