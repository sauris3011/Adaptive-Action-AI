"""The only place an embedding function is constructed.

Mirrors factory.py's rule for chat models. Three backends, tried in order, and
the choice is reported to the UI rather than hidden:

1. **gateway**  - the configured `embed` alias through the LiteLLM proxy, same
   TLS policy as every other call. This is the PRD 5.2 path.
2. **local**    - Chroma's bundled ONNX MiniLM. Used when the gateway serves no
   embedding model, which is the case on catalogues that expose chat models
   only. Still zero-daemon and zero-admin.
3. **hashed**   - a deterministic hashing embedder. Retrieval quality is poor
   and it is logged as degraded on every boot. It exists so a demo never dies
   because a model file could not be fetched, never as a silent default.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.config import get_settings
from app.logging_setup import get_logger
from app.tls import build_http_client

log = get_logger("llm.embeddings")

HASHED_DIM = 512


class Embedder(Protocol):
    name: str
    degraded: bool

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


# A live probe at selection time is bounded separately from real work: an
# unreachable gateway must cost the boot a few seconds, not the 120s an
# ingestion call is allowed to take.
PROBE_TIMEOUT_S = 20.0


class GatewayEmbedder:
    degraded = False

    def __init__(self, alias: str) -> None:
        settings = get_settings()
        self.name = f"gateway:{alias}"
        self._impl = self._build(alias, settings)
        self._probe(alias, settings)

    @staticmethod
    def _build(alias: str, settings, *, timeout: float | None = None):
        """A timeout means this is the throwaway probe client, which only ever
        makes one synchronous call - so it is not given an async client."""
        from langchain_openai import OpenAIEmbeddings

        kwargs = {} if timeout is None else {"timeout": timeout}
        return OpenAIEmbeddings(
            model=alias,
            base_url=settings.openai_base_url,
            api_key=settings.gateway_api_key or "sk-no-key-configured",
            http_client=build_http_client(**kwargs),
            http_async_client=None if timeout else build_http_client(is_async=True),
            check_embedding_ctx_length=False,
        )

    def _probe(self, alias: str, settings) -> None:
        """Confirm the gateway actually serves this alias, before it is chosen.

        Constructing OpenAIEmbeddings opens no connection, so without this the
        fallback chain in get_embedder() is dead code: a gateway that does not
        resolve is still "selected", and the failure surfaces mid-ingestion as
        an opaque APIConnectionError instead of a quiet downgrade to the local
        model.
        """
        self._build(alias, settings, timeout=PROBE_TIMEOUT_S).embed_query("probe")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._impl.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._impl.embed_query(text)


class LocalEmbedder:
    """Chroma's bundled all-MiniLM-L6-v2 ONNX model. No daemon, no admin."""

    degraded = False

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions

        self._fn = embedding_functions.DefaultEmbeddingFunction()
        self.name = "local:all-MiniLM-L6-v2"
        # Chroma defers building the ONNX session (and fetching the model) to
        # the first call, so without this a broken onnxruntime is discovered
        # mid-ingestion rather than here, where the hashed fallback still
        # applies. Also moves the one-time model download to selection time,
        # where it is attributable.
        self.embed_documents(["probe"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashedEmbedder:
    """Deterministic token-hashing with sublinear term weighting.

    Lexical only - it cannot match a paraphrase. Present so the pipeline stays
    runnable offline, and loud about being a downgrade.
    """

    degraded = True
    name = f"hashed:sha256-{HASHED_DIM}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * HASHED_DIM
        tokens = [t for t in "".join(
            c.lower() if c.isalnum() or c in "-." else " " for c in text
        ).split() if len(t) > 1]
        for token in tokens:
            idx = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % HASHED_DIM
            vec[idx] += 1.0
        vec = [math.log1p(v) for v in vec]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


_embedder: Embedder | None = None


def get_embedder(force: bool = False) -> Embedder:
    global _embedder
    if _embedder is not None and not force:
        return _embedder

    settings = get_settings()
    offline = settings.gateway_offline_reason
    alias = settings.model_embed.strip()

    if offline is not None:
        reason = offline
    elif not alias:
        reason = "no gateway embedding alias configured"
    else:
        reason = ""
        try:
            _embedder = GatewayEmbedder(alias)
            log.info("embedder_selected", backend=_embedder.name)
            return _embedder
        except Exception as exc:  # noqa: BLE001
            reason = f"gateway alias '{alias}' unreachable: {exc}"
            log.warning("embedder_gateway_unavailable", alias=alias, error=str(exc))

    try:
        _embedder = LocalEmbedder()
        log.info("embedder_selected", backend=_embedder.name, reason=reason)
        return _embedder
    except Exception as exc:  # noqa: BLE001
        log.warning("embedder_local_unavailable", error=str(exc))

    _embedder = HashedEmbedder()
    log.warning("embedder_degraded", backend=_embedder.name,
                detail="lexical hashing only; retrieval quality is materially reduced")
    return _embedder


def reset_embedder() -> None:
    """Called when the operator changes the embed alias in the settings drawer."""
    global _embedder
    _embedder = None


def describe() -> dict[str, object]:
    embedder = get_embedder()
    return {"backend": embedder.name, "degraded": embedder.degraded,
            "dimension": len(embedder.embed_query("probe"))}
