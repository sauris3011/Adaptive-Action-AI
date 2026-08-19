"""ChromaDB persistent vector store (PRD 5.5).

Local and file-based; no daemon. Embeddings are computed by app.llm.embeddings
and passed in explicitly rather than delegated to a Chroma embedding function,
so the gateway path and the TLS policy stay in one place.

Search returns Evidence, not raw dicts - the retrieval layer never hands the
reasoning layer an untyped blob.
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.llm.embeddings import get_embedder
from app.logging_setup import get_logger
from app.schemas.corpus import Chunk
from app.schemas.grounding import Evidence, EvidenceKind, Modality, SourceTier

log = get_logger("rag.store")

COLLECTION = "policy_corpus"
_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        settings.ensure_dirs()
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
    return _client


def _collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def upsert(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    embedder = get_embedder()
    vectors = embedder.embed_documents([c.text for c in chunks])
    _collection().upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=vectors,
        metadatas=[c.metadata() for c in chunks],
    )
    log.info("chunks_upserted", count=len(chunks), embedder=embedder.name)
    return len(chunks)


def search(query: str, k: int = 6, tier: SourceTier | None = None) -> list[Evidence]:
    collection = _collection()
    if collection.count() == 0:
        log.warning("vector_search_on_empty_collection", query_chars=len(query))
        return []

    where = {"tier": int(tier)} if tier is not None else None
    result = collection.query(
        query_embeddings=[get_embedder().embed_query(query)],
        n_results=min(k, collection.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return [
        _to_evidence(doc, meta, dist)
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def _to_evidence(document: str, meta: dict[str, Any], distance: float) -> Evidence:
    return Evidence(
        kind=EvidenceKind.POLICY,
        ref=str(meta.get("clause_id", "UNKNOWN")),
        title=str(meta.get("title", "")),
        content=document,
        modality=Modality(str(meta.get("modality", "text"))),
        tier=SourceTier(int(meta["tier"])) if meta.get("tier") else None,
        source_uri=str(meta.get("source_uri") or "") or None,
        # Cosine distance -> similarity. Reported for transparency in the UI,
        # never used as the reconciliation signal; precedence decides that.
        score=round(1.0 - float(distance), 4),
    )


def get_by_clause(clause_id: str) -> Evidence | None:
    """Exact clause lookup. Used when a recommendation cites an id and the UI
    needs the full text, without a similarity round trip."""
    result = _collection().get(
        where={"clause_id": clause_id}, include=["documents", "metadatas"], limit=1
    )
    if not result["ids"]:
        return None
    return _to_evidence(result["documents"][0], result["metadatas"][0], 0.0)


def stats() -> dict[str, Any]:
    """Feeds the grounding panel (FR-15)."""
    collection = _collection()
    total = collection.count()
    by_tier: dict[str, int] = {}
    by_doc: dict[str, int] = {}
    if total:
        for meta in collection.get(include=["metadatas"])["metadatas"]:
            label = str(meta.get("tier_label", "untiered"))
            by_tier[label] = by_tier.get(label, 0) + 1
            doc = str(meta.get("doc_id", "?"))
            by_doc[doc] = by_doc.get(doc, 0) + 1
    from app.llm import embeddings as emb

    return {
        "collection": COLLECTION,
        "chunks": total,
        "documents": len(by_doc),
        "by_tier": by_tier,
        "by_document": by_doc,
        "embedder": emb.describe(),
        "path": str(get_settings().chroma_dir),
    }


def reset() -> None:
    """Full re-seed. Deleting the collection is cheaper and more predictable
    than reconciling ids against a corpus that may have lost a clause."""
    try:
        _get_client().delete_collection(COLLECTION)
    except Exception:  # noqa: BLE001 - absent collection is the desired end state
        pass
    log.info("vector_store_reset")
