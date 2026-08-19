"""GraphStore contract and backend selection (PRD 5.5).

A FIXED five-query surface, deliberately not a Cypher passthrough: Kuzu's Cypher
dialect diverges from Neo4j's, and a passthrough would make maintaining the
second backend unaffordable. Adding a query means adding it to both
implementations, which is the intended friction.

Backend choice is resolved ONCE at boot from a reachability probe, not lazily on
first use - a demo must not discover a dead cloud dependency mid-request.
Implementations land in Stage 2; this module owns the contract and the choice.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.config import get_settings
from app.logging_setup import get_logger

log = get_logger("graph.base")

_active: str | None = None


@runtime_checkable
class GraphStore(Protocol):
    """The complete query surface. Both backends implement exactly this."""

    def customer_dispute_history(self, customer_id: str) -> list[dict[str, Any]]: ...

    def merchant_risk_profile(self, merchant_id: str) -> dict[str, Any] | None: ...

    def policy_dependencies(self, clause_id: str) -> list[dict[str, Any]]: ...

    def transaction_context(self, transaction_id: str) -> dict[str, Any] | None: ...

    def neighborhood(self, entity_id: str, hops: int = 2) -> dict[str, Any]: ...

    # Introspection and writes. Outside the five reasoning queries, but both
    # backends must still implement them identically or the seed diverges.
    def upsert_nodes(self, rows: list[Any]) -> int: ...

    def upsert_rels(self, rows: list[Any]) -> int: ...

    def keys(self, label: str) -> list[str]: ...

    def node_by_key(self, key_value: str) -> dict[str, Any] | None: ...

    def edges_of(self, key_value: str) -> list[dict[str, str]]: ...

    def clear(self) -> None: ...

    def counts(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


def probe_neo4j(timeout_s: float = 5.0) -> tuple[bool, str]:
    """Reachability probe used by pre-flight and boot. Never raises."""
    settings = get_settings()
    if not settings.neo4j_uri:
        return False, "NEO4J_URI not set"
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=timeout_s,
        )
        try:
            driver.verify_connectivity()
            return True, "reachable"
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001 - any failure means "use the fallback"
        return False, f"{type(exc).__name__}: {exc}"


def select_backend() -> str:
    """Resolve neo4j vs kuzu. Loud about falling back - never a silent downgrade."""
    global _active
    settings = get_settings()

    if settings.graph_backend == "kuzu":
        _active = "kuzu"
    elif settings.graph_backend == "neo4j":
        ok, detail = probe_neo4j()
        if not ok:
            # Explicit neo4j is a stated intent; refusing to silently downgrade
            # is the difference between a clear boot failure and a confusing demo.
            raise RuntimeError(f"GRAPH_BACKEND=neo4j but Neo4j is unreachable: {detail}")
        _active = "neo4j"
    else:  # auto
        ok, detail = probe_neo4j()
        _active = "neo4j" if ok else "kuzu"
        if not ok:
            log.warning("graph_fallback", backend="kuzu", reason=detail)

    log.info("graph_backend_selected", backend=_active)
    return _active


def active_backend() -> str:
    return _active or "unselected"


_store: Any | None = None


def get_store() -> GraphStore:
    """Singleton over the backend chosen at boot.

    Construction is lazy but selection is not: select_backend() already ran in
    the lifespan hook, so a dead cloud dependency has surfaced before the first
    request rather than inside it.
    """
    global _store
    if _store is not None:
        return _store

    backend = _active or select_backend()
    if backend == "neo4j":
        from app.graph.neo4j_store import Neo4jStore

        _store = Neo4jStore()
    else:
        from app.graph.kuzu_store import KuzuStore

        _store = KuzuStore()
    return _store


def close_store() -> None:
    """Graceful shutdown (FR-23)."""
    global _store
    if _store is not None:
        _store.close()
        _store = None
