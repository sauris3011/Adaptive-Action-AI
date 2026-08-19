"""Ingestion flow: load -> chunk -> embed -> index -> extract to graph.

The flow itself is modality-agnostic. It asks the registry for a loader and
never branches on file type (PRD 8.1 provision 1). A new modality registers a
handler in loaders.py; this file does not change.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPO_ROOT, get_settings
from app.logging_setup import get_logger
from app.rag import store
from app.rag.chunker import chunk_document
from app.rag.loaders import UnsupportedModality, load
from app.schemas.corpus import Chunk, Document

log = get_logger("rag.ingest")

CORPUS_DIR = REPO_ROOT / "backend" / "domain" / "banking" / "corpus"


@dataclass
class IngestResult:
    documents: list[Document] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {"documents": len(self.documents), "chunks": len(self.chunks),
                "skipped": len(self.skipped)}


def ingest_path(path: Path, result: IngestResult | None = None) -> IngestResult:
    result = result or IngestResult()
    try:
        doc = load(path)
    except UnsupportedModality as exc:
        # Accepted and recorded, not interpreted (PRD 8.1). A rejected upload
        # would lose the attachment; skipping keeps it referenceable.
        result.skipped.append({"path": path.name, "reason": str(exc), "mime": exc.mime})
        log.warning("ingest_skipped", path=path.name, mime=exc.mime)
        return result
    except ValueError as exc:
        result.skipped.append({"path": path.name, "reason": str(exc), "mime": ""})
        log.warning("ingest_rejected", path=path.name, error=str(exc))
        return result

    chunks = chunk_document(doc)
    if not chunks:
        result.skipped.append({"path": path.name, "reason": "no chunkable content", "mime": ""})
        return result

    store.upsert(chunks)
    result.documents.append(doc)
    result.chunks.extend(chunks)
    log.info("document_ingested", doc_id=doc.doc_id, chunks=len(chunks), tier=int(doc.tier))
    return result


def ingest_corpus(directory: Path | None = None, reset: bool = False) -> IngestResult:
    directory = directory or CORPUS_DIR
    if reset:
        store.reset()
    result = IngestResult()
    for path in sorted(directory.glob("*")):
        if path.is_file():
            ingest_path(path, result)
    log.info("corpus_ingested", **result.summary)
    return result


def ingest_upload(filename: str, payload: bytes) -> IngestResult:
    """Dynamic upload (FR-15). The file is persisted before parsing so that a
    document we cannot yet interpret is still stored and citable by URI."""
    settings = get_settings()
    settings.ensure_dirs()
    safe = Path(filename).name.replace("..", "_")
    target = settings.upload_dir / safe
    target.write_bytes(payload)
    log.info("upload_stored", filename=safe, bytes=len(payload))

    result = ingest_path(target)
    if result.documents:
        from app.graph import extract

        extract.extract_documents(result.documents, result.chunks)
    return result


def clear_uploads() -> int:
    upload_dir = get_settings().upload_dir
    if not upload_dir.exists():
        return 0
    count = len(list(upload_dir.glob("*")))
    shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return count
