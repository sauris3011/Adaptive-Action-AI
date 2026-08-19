"""Clause-aware chunking.

The clause heading IS the chunk boundary. Fixed-window chunking would split a
clause mid-sentence and make `clause_id` a guess; here it is exact, which is
what FR-5 ("cite at least one governing clause by ID") actually requires.

A document with no clause headings falls back to paragraph windows and carries a
synthetic clause id, so an uploaded document still ingests.
"""

from __future__ import annotations

import re

from app.schemas.corpus import Chunk, Document

# "## BDP-4.2 — Provisional credit timing" (em dash, en dash or hyphen).
CLAUSE_HEADING = re.compile(
    r"^#{1,6}\s+(?P<clause>[A-Z][A-Z0-9]*(?:-[A-Za-z0-9.]+)+)\s*[—–-]?\s*(?P<title>.*)$"
)

MAX_CHARS = 1800
MIN_CHARS = 40


def _window(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split on paragraph boundaries without exceeding `limit`."""
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) > limit and current:
            parts.append(current)
            current = para
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_document(doc: Document) -> list[Chunk]:
    sections: list[tuple[str, str, list[str]]] = []
    preamble: list[str] = []

    for line in doc.text.splitlines():
        match = CLAUSE_HEADING.match(line.strip())
        if match:
            sections.append((match.group("clause"), match.group("title").strip(), []))
        elif sections:
            sections[-1][2].append(line)
        else:
            preamble.append(line)

    if not sections:
        return _fallback(doc, "\n".join(preamble) or doc.text)

    chunks: list[Chunk] = []
    for ordinal, (clause_id, title, body_lines) in enumerate(sections):
        body = "\n".join(body_lines).strip()
        if len(body) < MIN_CHARS:
            continue
        for part in _window(body):
            chunks.append(
                Chunk(
                    chunk_id=Chunk.make_id(doc.doc_id, clause_id, part),
                    doc_id=doc.doc_id,
                    clause_id=clause_id,
                    title=title or doc.title,
                    tier=doc.tier,
                    modality=doc.modality,
                    source_uri=doc.source_uri,
                    text=f"{clause_id} — {title}\n\n{part}" if title else part,
                    ordinal=ordinal,
                )
            )
    return chunks


def _fallback(doc: Document, text: str) -> list[Chunk]:
    """No clause headings: synthesise ids so uploads still cite something
    specific. `DOC-p1` is honest about being positional, not a real clause."""
    chunks = []
    for ordinal, part in enumerate(_window(text), start=1):
        if len(part) < MIN_CHARS:
            continue
        clause_id = f"{doc.doc_id}-p{ordinal}"
        chunks.append(
            Chunk(
                chunk_id=Chunk.make_id(doc.doc_id, clause_id, part),
                doc_id=doc.doc_id,
                clause_id=clause_id,
                title=doc.title,
                tier=doc.tier,
                modality=doc.modality,
                source_uri=doc.source_uri,
                text=part,
                ordinal=ordinal,
            )
        )
    return chunks
