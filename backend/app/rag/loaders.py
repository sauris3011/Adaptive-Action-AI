"""MIME-keyed loader registry (PRD 8.1 provision 1).

Adding a modality is a REGISTRATION, not an edit to the ingestion flow. That is
the whole point of this module: `ingest.py` never grows an if-chain over file
types. Image and table handlers are reserved and deliberately absent - they are
accepted, stored and surfaced in the trace, but not yet interpreted (PRD 8.1).
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path

from app.logging_setup import get_logger
from app.schemas.corpus import Document
from app.schemas.grounding import Modality, SourceTier

log = get_logger("rag.loaders")

Loader = Callable[[Path], Document]
_REGISTRY: dict[str, Loader] = {}

# Extensions the OS may not map consistently across platforms.
_EXTRA_TYPES = {".md": "text/markdown", ".txt": "text/plain"}


def register(*mime_types: str) -> Callable[[Loader], Loader]:
    def decorator(fn: Loader) -> Loader:
        for mime in mime_types:
            _REGISTRY[mime] = fn
        return fn
    return decorator


def guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _EXTRA_TYPES:
        return _EXTRA_TYPES[suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def supported_mimes() -> list[str]:
    return sorted(_REGISTRY)


class UnsupportedModality(ValueError):
    """Raised for a MIME type with no registered handler. Names what IS
    supported, because 'unsupported file' with no list is a dead end."""

    def __init__(self, mime: str) -> None:
        super().__init__(
            f"no loader registered for '{mime}'; supported: {', '.join(supported_mimes())}"
        )
        self.mime = mime


def load(path: Path) -> Document:
    mime = guess_mime(path)
    loader = _REGISTRY.get(mime)
    if loader is None:
        raise UnsupportedModality(mime)
    doc = loader(path)
    log.info("document_loaded", doc_id=doc.doc_id, mime=mime,
             tier=int(doc.tier), chars=len(doc.text))
    return doc


# --------------------------------------------------------------------------
# Front matter
# --------------------------------------------------------------------------

def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Minimal `---` delimited key: value block. Not YAML - the corpus format is
    ours, and a YAML dependency to read six flat keys is not worth its weight."""
    if not text.startswith("---"):
        return {}, text
    _, _, rest = text.partition("---\n")
    block, sep, body = rest.partition("\n---")
    if not sep:
        return {}, text
    meta: dict[str, str] = {}
    for line in block.splitlines():
        key, delim, value = line.partition(":")
        if delim:
            meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def _tier_from(meta: dict[str, str], path: Path) -> SourceTier:
    raw = meta.get("tier", "").strip()
    if not raw:
        # An untiered document cannot participate in precedence resolution, so
        # it must not be silently admitted at an arbitrary rank.
        raise ValueError(
            f"{path.name}: missing 'tier' in front matter. Precedence is a property "
            f"of the corpus (PRD 5.4); an untiered document cannot be reconciled."
        )
    try:
        return SourceTier(int(raw))
    except (ValueError, KeyError) as exc:
        valid = {int(t): t.label for t in SourceTier}
        raise ValueError(f"{path.name}: tier '{raw}' invalid; expected one of {valid}") from exc


@register("text/markdown", "text/plain")
def load_text(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(raw)
    return Document(
        doc_id=meta.get("doc_id") or path.stem.upper(),
        title=meta.get("title") or path.stem.replace("_", " ").title(),
        tier=_tier_from(meta, path),
        modality=Modality.TEXT,
        source_uri=path.as_posix(),
        authority=meta.get("authority", ""),
        effective=meta.get("effective", ""),
        text=body,
        meta={k: v for k, v in meta.items()
              if k not in {"doc_id", "title", "tier", "authority", "effective"}},
    )
