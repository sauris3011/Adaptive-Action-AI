"""Grounding panel endpoints (FR-15).

Everything the panel shows is read back from the stores, never cached in the
API layer: the panel is the operator's evidence that seeding worked, so it must
be capable of disagreeing with the seed script's output.

Upload is synchronous. At corpus scale that is well inside a request, and a job
queue would add a moving part with no user-visible benefit.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.db import records
from app.graph import extract, traverse
from app.graph.base import active_backend, get_store
from app.logging_setup import get_logger
from app.rag import ingest, loaders
from app.rag import store as vector_store
from app.rag.retrieve import retrieve

router = APIRouter(prefix="/api/grounding", tags=["grounding"])
log = get_logger("api.grounding")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("/stats")
def stats() -> dict[str, Any]:
    """Vector, graph and relational counts in one call - the panel polls this."""
    store = get_store()
    return {
        "vector": vector_store.stats(),
        "graph": store.counts() | {"active_backend": active_backend()},
        "relational": records.counts(),
        "supported_uploads": loaders.supported_mimes(),
    }


@router.get("/graph")
def graph_view(
    entity: str | None = Query(default=None, description="Entity key to centre on"),
    hops: int = Query(default=2, ge=1, le=3),
) -> dict[str, Any]:
    """Force-graph payload. No `entity` returns the whole seed graph."""
    store = get_store()
    if entity:
        result = store.neighborhood(entity, hops)
        if not result["found"]:
            raise HTTPException(status_code=404, detail=f"no node with key '{entity}'")
        return result
    return traverse.overview(store)


@router.get("/search")
def search(
    q: str = Query(min_length=2),
    k: int = Query(default=6, ge=1, le=20),
    transaction_id: str | None = None,
) -> dict[str, Any]:
    """Retrieval preview: exactly the fan-out the agent will use in Stage 3.

    Exposed because a grounding panel that cannot show what a query retrieves
    only proves the stores are populated, not that they are useful.
    """
    context = retrieve(q, transaction_id=transaction_id, k=k)
    return {
        "query": q,
        "count": len(context.evidence),
        "evidence": [e.model_dump(mode="json") for e in context.by_precedence()],
    }


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file is {len(payload)} bytes; limit is {MAX_UPLOAD_BYTES}",
        )
    if not payload:
        raise HTTPException(status_code=400, detail="empty file")

    result = ingest.ingest_upload(file.filename or "upload.bin", payload)
    if not result.documents and result.skipped:
        # 422 rather than 500: the file was stored and is referenceable, we
        # simply cannot interpret it yet (PRD 8.1).
        raise HTTPException(status_code=422, detail=result.skipped[0]["reason"])

    return {
        "filename": file.filename,
        "documents": [d.doc_id for d in result.documents],
        "chunks": len(result.chunks),
        "skipped": result.skipped,
        "stats": vector_store.stats(),
    }


@router.post("/reseed")
def reseed(reset: bool = Query(default=True)) -> dict[str, Any]:
    """Re-run the domain-pack seed from the UI.

    The demo's recovery path: a mis-seeded store is one button away from correct
    without dropping to a terminal mid-presentation.
    """
    store = get_store()
    fixture = extract.load_records()
    if reset:
        store.clear()
        records.clear()
        vector_store.reset()

    records.load(fixture)
    result = ingest.ingest_corpus(reset=False)
    extract.extract_documents(result.documents, result.chunks)
    extract.extract_records(fixture)
    edges = extract.extract_policy_edges(fixture)
    log.info("reseed_complete", documents=len(result.documents),
             chunks=len(result.chunks), policy_edges=edges)

    return {
        "documents": len(result.documents),
        "chunks": len(result.chunks),
        "policy_edges": edges,
        "skipped": result.skipped,
        "vector": vector_store.stats(),
        "graph": store.counts(),
        "relational": records.counts(),
    }
