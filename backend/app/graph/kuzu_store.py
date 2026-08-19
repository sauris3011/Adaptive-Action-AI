"""Embedded Kuzu backend - the fallback that must never be second-class.

Acceptance criterion 9 requires the golden path to pass with Neo4j credentials
unset, so this implementation is developed first and the Neo4j one is held to
matching its results.

`neighborhood` is a Python BFS over a per-node edge primitive rather than a
variable-length Cypher pattern. That is deliberate: recursive-pattern syntax is
exactly where the two dialects diverge, and a BFS built from single-hop queries
is identical on both backends by construction.
"""

from __future__ import annotations

from typing import Any

import kuzu

from app.config import get_settings
from app.graph.schema import (NODE_BY_LABEL, NODES, POLICY_REL_LABELS, RELS,
                              NodeRow, RelRow, coerce)
from app.logging_setup import get_logger

log = get_logger("graph.kuzu")


class KuzuStore:
    backend = "kuzu"

    def __init__(self) -> None:
        settings = get_settings()
        settings.ensure_dirs()
        self._db = kuzu.Database(str(settings.kuzu_dir / "graph"))
        self._conn = kuzu.Connection(self._db)
        self._ensure_schema()

    # -- setup -------------------------------------------------------------
    def _ensure_schema(self) -> None:
        for node in NODES:
            cols = ", ".join(f"{n} {t}" for n, t in node.props.items())
            self._conn.execute(
                f"CREATE NODE TABLE IF NOT EXISTS {node.label}({cols}, PRIMARY KEY ({node.key}))"
            )
        for rel in RELS:
            extra = "".join(f", {n} {t}" for n, t in rel.props.items())
            self._conn.execute(
                f"CREATE REL TABLE IF NOT EXISTS {rel.label}(FROM {rel.src} TO {rel.dst}{extra})"
            )

    def _rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = self._conn.execute(cypher, parameters=params or {})
        return [dict(r) for r in result.rows_as_dict()]

    # -- writes ------------------------------------------------------------
    def upsert_nodes(self, rows: list[NodeRow]) -> int:
        for row in rows:
            spec = next(n for n in NODES if n.label == row.label)
            props = coerce(row.label, row.props)
            # Kuzu refuses to SET a primary key, even to its current value, so
            # the key is matched on and every other property is assigned.
            assigns = ", ".join(f"n.{n} = ${n}" for n in props if n != spec.key)
            clause = f" ON CREATE SET {assigns} ON MATCH SET {assigns}" if assigns else ""
            self._conn.execute(
                f"MERGE (n:{row.label} {{{spec.key}: ${spec.key}}}){clause}",
                parameters=props,
            )
        return len(rows)

    def upsert_rels(self, rows: list[RelRow]) -> int:
        written = 0
        for row in rows:
            spec = next(r for r in RELS if r.label == row.label)
            src_key = next(n for n in NODES if n.label == spec.src).key
            dst_key = next(n for n in NODES if n.label == spec.dst).key
            params: dict[str, Any] = {"src": row.src_key, "dst": row.dst_key}
            setters = ""
            if spec.props:
                params |= {k: str(row.props.get(k, "")) for k in spec.props}
                setters = " SET " + ", ".join(f"e.{k} = ${k}" for k in spec.props)
            try:
                self._conn.execute(
                    f"MATCH (a:{spec.src} {{{src_key}: $src}}), "
                    f"(b:{spec.dst} {{{dst_key}: $dst}}) "
                    f"MERGE (a)-[e:{row.label}]->(b){setters}",
                    parameters=params,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001 - a dangling edge is data, not a crash
                log.warning("rel_skipped", label=row.label, src=row.src_key,
                            dst=row.dst_key, error=str(exc))
        return written

    def clear(self) -> None:
        for rel in RELS:
            self._conn.execute(f"MATCH ()-[e:{rel.label}]->() DELETE e")
        for node in NODES:
            self._conn.execute(f"MATCH (n:{node.label}) DELETE n")

    def delete_nodes(self, label: str, keys: list[str]) -> int:
        """Kuzu has no DETACH DELETE, so the edges go first - the same order
        clear() uses, and the reason a node with edges cannot just be dropped."""
        if not keys:
            return 0
        spec = NODE_BY_LABEL[label]
        touching = [r for r in RELS if label in (r.src, r.dst)]
        for key in keys:
            for rel in touching:
                side = "a" if rel.src == label else "b"
                self._conn.execute(
                    f"MATCH (a:{rel.src})-[e:{rel.label}]->(b:{rel.dst}) "
                    f"WHERE {side}.{spec.key} = $key DELETE e",
                    parameters={"key": key},
                )
            self._conn.execute(
                f"MATCH (n:{label}) WHERE n.{spec.key} = $key DELETE n",
                parameters={"key": key},
            )
        log.info("nodes_deleted", label=label, count=len(keys))
        return len(keys)

    # -- the fixed five-query surface --------------------------------------
    def customer_dispute_history(self, customer_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "MATCH (c:Customer {customer_id: $cid})-[:RAISED]->(d:Dispute) "
            "RETURN d.dispute_id AS dispute_id, d.transaction_id AS transaction_id, "
            "d.reason_code AS reason_code, d.amount AS amount, "
            "d.opened_at AS opened_at, d.outcome AS outcome "
            "ORDER BY d.opened_at DESC",
            {"cid": customer_id},
        )

    def merchant_risk_profile(self, merchant_id: str) -> dict[str, Any] | None:
        rows = self._rows(
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
                for r in self._rows(
                    f"MATCH (a:Policy {{clause_id: $cid}})-[e:{label}]->(b:Policy) "
                    f"RETURN b.clause_id AS clause_id, b.title AS title, "
                    f"b.tier AS tier, b.tier_label AS tier_label, e.note AS note",
                    {"cid": clause_id},
                )
            ]
            out += [
                dict(r, relation=label, direction="incoming")
                for r in self._rows(
                    f"MATCH (a:Policy)-[e:{label}]->(b:Policy {{clause_id: $cid}}) "
                    f"RETURN a.clause_id AS clause_id, a.title AS title, "
                    f"a.tier AS tier, a.tier_label AS tier_label, e.note AS note",
                    {"cid": clause_id},
                )
            ]
        return out

    def transaction_context(self, transaction_id: str) -> dict[str, Any] | None:
        rows = self._rows(
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
            rows = self._rows(
                f"MATCH (n:{node.label} {{{node.key}: $v}}) RETURN n.*",
                {"v": key_value},
            )
            if rows:
                props = {k.removeprefix("n."): v for k, v in rows[0].items()}
                return {"id": key_value, "label": node.label,
                        "caption": str(props.get(node.display, key_value)),
                        "props": props}
        return None

    def edges_of(self, key_value: str) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for rel in RELS:
            src_key = next(n for n in NODES if n.label == rel.src).key
            dst_key = next(n for n in NODES if n.label == rel.dst).key
            for row in self._rows(
                f"MATCH (a:{rel.src} {{{src_key}: $v}})-[:{rel.label}]->(b:{rel.dst}) "
                f"RETURN b.{dst_key} AS other", {"v": key_value},
            ):
                edges.append({"source": key_value, "target": str(row["other"]),
                              "label": rel.label})
            for row in self._rows(
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
                self._rows(f"MATCH (n:{label}) RETURN n.{spec.key} AS k")]

    def counts(self) -> dict[str, Any]:
        nodes = {n.label: int(self._rows(f"MATCH (n:{n.label}) RETURN count(n) AS c")[0]["c"])
                 for n in NODES}
        rels = {r.label: int(self._rows(f"MATCH ()-[e:{r.label}]->() RETURN count(e) AS c")[0]["c"])
                for r in RELS}
        return {"backend": self.backend, "nodes": sum(nodes.values()),
                "relationships": sum(rels.values()),
                "by_label": nodes, "by_relationship": rels}

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 - teardown must not raise
            pass
