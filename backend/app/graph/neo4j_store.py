"""Neo4j Aura backend.

Held to the Kuzu implementation's results, not the other way round: the fallback
is the one guaranteed to be available, so it defines the contract. Same fixed
five-query surface, same shared BFS for `neighborhood`.

The free-tier ceiling (50k nodes / 175k relationships) is roughly two orders of
magnitude above the seed corpus, so no partitioning is required (PRD 5.5).
"""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from app.config import get_settings
from app.graph.schema import (NODE_BY_LABEL, NODES, POLICY_REL_LABELS, RELS,
                              NodeRow, RelRow, coerce)
from app.logging_setup import get_logger

log = get_logger("graph.neo4j")


class Neo4jStore:
    backend = "neo4j"

    def __init__(self) -> None:
        settings = get_settings()
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            # TLS to Aura is neo4j+s and terminates at Aura, not at the corporate
            # proxy, so app.tls does not apply here.
            connection_timeout=15.0,
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Uniqueness constraints only. Neo4j is schema-optional; the property
        shapes come from schema.py via coerce(), which is what keeps the two
        backends storing the same graph."""
        for node in NODES:
            self._run(
                f"CREATE CONSTRAINT {node.label.lower()}_key IF NOT EXISTS "
                f"FOR (n:{node.label}) REQUIRE n.{node.key} IS UNIQUE"
            )

    def _run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            return [r.data() for r in session.run(cypher, **(params or {}))]

    # -- writes ------------------------------------------------------------
    def upsert_nodes(self, rows: list[NodeRow]) -> int:
        for row in rows:
            spec = next(n for n in NODES if n.label == row.label)
            props = coerce(row.label, row.props)
            self._run(
                f"MERGE (n:{row.label} {{{spec.key}: $key}}) SET n += $props",
                {"key": props[spec.key], "props": props},
            )
        return len(rows)

    def upsert_rels(self, rows: list[RelRow]) -> int:
        written = 0
        for row in rows:
            spec = next(r for r in RELS if r.label == row.label)
            src_key = next(n for n in NODES if n.label == spec.src).key
            dst_key = next(n for n in NODES if n.label == spec.dst).key
            props = {k: str(row.props.get(k, "")) for k in spec.props}
            result = self._run(
                f"MATCH (a:{spec.src} {{{src_key}: $src}}), "
                f"(b:{spec.dst} {{{dst_key}: $dst}}) "
                f"MERGE (a)-[e:{row.label}]->(b) SET e += $props RETURN 1 AS ok",
                {"src": row.src_key, "dst": row.dst_key, "props": props},
            )
            if result:
                written += 1
            else:
                log.warning("rel_skipped", label=row.label, src=row.src_key, dst=row.dst_key)
        return written

    def clear(self) -> None:
        self._run("MATCH (n) DETACH DELETE n")

    def delete_nodes(self, label: str, keys: list[str]) -> int:
        if not keys:
            return 0
        spec = NODE_BY_LABEL[label]
        self._run(
            f"MATCH (n:{label}) WHERE n.{spec.key} IN $keys DETACH DELETE n",
            {"keys": list(keys)},
        )
        log.info("nodes_deleted", label=label, count=len(keys))
        return len(keys)

    # -- the fixed five-query surface --------------------------------------
    def customer_dispute_history(self, customer_id: str) -> list[dict[str, Any]]:
        return self._run(
            "MATCH (c:Customer {customer_id: $cid})-[:RAISED]->(d:Dispute) "
            "RETURN d.dispute_id AS dispute_id, d.transaction_id AS transaction_id, "
            "d.reason_code AS reason_code, d.amount AS amount, "
            "d.opened_at AS opened_at, d.outcome AS outcome "
            "ORDER BY d.opened_at DESC",
            {"cid": customer_id},
        )

    def merchant_risk_profile(self, merchant_id: str) -> dict[str, Any] | None:
        rows = self._run(
            "MATCH (m:Merchant {merchant_id: $mid}) "
            "OPTIONAL MATCH (t:Transaction)-[:AT]->(m) "
            "RETURN m.merchant_id AS merchant_id, m.name AS name, "
            "m.category AS category, m.country AS country, "
            "m.dispute_rate AS dispute_rate, m.risk_band AS risk_band, "
            "count(t) AS transaction_count",
            {"mid": merchant_id},
        )
        return rows[0] if rows else None

    def policy_dependencies(self, clause_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for label in POLICY_REL_LABELS:
            out += [
                dict(r, relation=label, direction="outgoing")
                for r in self._run(
                    f"MATCH (a:Policy {{clause_id: $cid}})-[e:{label}]->(b:Policy) "
                    f"RETURN b.clause_id AS clause_id, b.title AS title, "
                    f"b.tier AS tier, b.tier_label AS tier_label, e.note AS note",
                    {"cid": clause_id},
                )
            ]
            out += [
                dict(r, relation=label, direction="incoming")
                for r in self._run(
                    f"MATCH (a:Policy)-[e:{label}]->(b:Policy {{clause_id: $cid}}) "
                    f"RETURN a.clause_id AS clause_id, a.title AS title, "
                    f"a.tier AS tier, a.tier_label AS tier_label, e.note AS note",
                    {"cid": clause_id},
                )
            ]
        return out

    def transaction_context(self, transaction_id: str) -> dict[str, Any] | None:
        rows = self._run(
            "MATCH (c:Customer)-[:HOLDS]->(a:Account)-[:MADE]->"
            "(t:Transaction {transaction_id: $tid}) "
            "OPTIONAL MATCH (t)-[:AT]->(m:Merchant) "
            "RETURN t.transaction_id AS transaction_id, t.amount AS amount, "
            "t.currency AS currency, t.posted_at AS posted_at, "
            "t.channel AS channel, t.fraud_flag AS fraud_flag, "
            "t.fraud_score AS fraud_score, t.status AS status, "
            "a.account_id AS account_id, a.product AS product, "
            "a.opened AS account_opened, c.customer_id AS customer_id, "
            "c.name AS customer_name, c.product_tier AS product_tier, "
            "m.merchant_id AS merchant_id, m.name AS merchant_name, "
            "m.risk_band AS merchant_risk_band",
            {"tid": transaction_id},
        )
        return rows[0] if rows else None

    def neighborhood(self, entity_id: str, hops: int = 2) -> dict[str, Any]:
        from app.graph.traverse import bfs

        return bfs(self, entity_id, hops)

    # -- primitives the shared BFS is built from ---------------------------
    def node_by_key(self, key_value: str) -> dict[str, Any] | None:
        for node in NODES:
            rows = self._run(
                f"MATCH (n:{node.label} {{{node.key}: $v}}) RETURN properties(n) AS p",
                {"v": key_value},
            )
            if rows:
                props = rows[0]["p"]
                return {"id": key_value, "label": node.label,
                        "caption": str(props.get(node.display, key_value)),
                        "props": props}
        return None

    def edges_of(self, key_value: str) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for rel in RELS:
            src_key = next(n for n in NODES if n.label == rel.src).key
            dst_key = next(n for n in NODES if n.label == rel.dst).key
            for row in self._run(
                f"MATCH (a:{rel.src} {{{src_key}: $v}})-[:{rel.label}]->(b:{rel.dst}) "
                f"RETURN b.{dst_key} AS other", {"v": key_value},
            ):
                edges.append({"source": key_value, "target": str(row["other"]),
                              "label": rel.label})
            for row in self._run(
                f"MATCH (a:{rel.src})-[:{rel.label}]->(b:{rel.dst} {{{dst_key}: $v}}) "
                f"RETURN a.{src_key} AS other", {"v": key_value},
            ):
                edges.append({"source": str(row["other"]), "target": key_value,
                              "label": rel.label})
        return edges

    def keys(self, label: str) -> list[str]:
        """Introspection, not a reasoning query - it backs the grounding panel's
        overview, and is deliberately outside the fixed five-query surface."""
        spec = NODE_BY_LABEL[label]
        return [str(r["k"]) for r in
                self._run(f"MATCH (n:{label}) RETURN n.{spec.key} AS k")]

    def counts(self) -> dict[str, Any]:
        nodes = {n.label: self._run(f"MATCH (n:{n.label}) RETURN count(n) AS c")[0]["c"]
                 for n in NODES}
        rels = {r.label: self._run(f"MATCH ()-[e:{r.label}]->() RETURN count(e) AS c")[0]["c"]
                for r in RELS}
        return {"backend": self.backend, "nodes": sum(nodes.values()),
                "relationships": sum(rels.values()),
                "by_label": nodes, "by_relationship": rels}

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
