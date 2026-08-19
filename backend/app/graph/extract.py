"""Extraction pipeline: fixtures and documents into the knowledge graph.

Two sources, one graph:

* **Entity extraction is deterministic.** Customers, accounts, merchants,
  transactions and disputes come from the records fixture, not from an LLM.
  Hallucinating a fraud flag would be worse than not having one, and these
  facts already exist in structured form - inferring them would be a
  self-inflicted accuracy problem.
* **Policy extraction is structural.** A Policy node per clause, keyed on the
  clause id the chunker already produced, with tier carried through from
  ingestion. Clause-to-clause edges come from the domain pack, so precedence
  relationships stay a property of the corpus (PRD 5.4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.graph.base import get_store
from app.graph.schema import NodeRow, RelRow
from app.logging_setup import get_logger
from app.schemas.corpus import Chunk, Document

log = get_logger("graph.extract")

RECORDS_PATH = REPO_ROOT / "backend" / "domain" / "banking" / "records.json"


def load_records(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or RECORDS_PATH).read_text(encoding="utf-8"))


def extract_records(records: dict[str, Any] | None = None) -> dict[str, int]:
    records = records or load_records()
    store = get_store()

    nodes: list[NodeRow] = []
    for customer in records.get("customers", []):
        nodes.append(NodeRow("Customer", customer["customer_id"], customer))
    for account in records.get("accounts", []):
        nodes.append(NodeRow("Account", account["account_id"], account))
    for merchant in records.get("merchants", []):
        nodes.append(NodeRow("Merchant", merchant["merchant_id"], merchant))
    for txn in records.get("transactions", []):
        nodes.append(NodeRow("Transaction", txn["transaction_id"], txn))
    for dispute in records.get("disputes", []):
        nodes.append(NodeRow("Dispute", dispute["dispute_id"], dispute))
    store.upsert_nodes(nodes)

    rels: list[RelRow] = []
    for account in records.get("accounts", []):
        rels.append(RelRow("HOLDS", account["customer_id"], account["account_id"]))
    for txn in records.get("transactions", []):
        rels.append(RelRow("MADE", txn["account_id"], txn["transaction_id"]))
        rels.append(RelRow("AT", txn["transaction_id"], txn["merchant_id"]))
    for dispute in records.get("disputes", []):
        rels.append(RelRow("RAISED", dispute["customer_id"], dispute["dispute_id"]))
    written = store.upsert_rels(rels)

    log.info("records_extracted", nodes=len(nodes), relationships=written)
    return {"nodes": len(nodes), "relationships": written}


def extract_documents(documents: list[Document], chunks: list[Chunk]) -> dict[str, int]:
    """One Policy node per clause. Chunks already carry clause id and tier, so
    this is a projection, not an inference."""
    store = get_store()
    seen: dict[str, NodeRow] = {}
    titles = {doc.doc_id: doc.title for doc in documents}

    for chunk in chunks:
        if chunk.clause_id in seen:
            continue
        seen[chunk.clause_id] = NodeRow("Policy", chunk.clause_id, {
            "clause_id": chunk.clause_id,
            "doc_id": chunk.doc_id,
            "title": chunk.title or titles.get(chunk.doc_id, ""),
            "tier": int(chunk.tier),
            "tier_label": chunk.tier.label,
            "source_uri": chunk.source_uri,
        })
    store.upsert_nodes(list(seen.values()))
    log.info("policy_nodes_extracted", clauses=len(seen))
    return {"clauses": len(seen)}


def extract_policy_edges(records: dict[str, Any] | None = None) -> int:
    """Clause-to-clause edges from the domain pack.

    Edges whose endpoints are not both present are skipped by the store and
    logged, so a corpus edit that drops a clause is visible rather than silent.
    """
    records = records or load_records()
    rels = [
        RelRow(edge["type"], edge["from"], edge["to"], {"note": edge.get("note", "")})
        for edge in records.get("policy_edges", [])
    ]
    written = get_store().upsert_rels(rels)
    log.info("policy_edges_extracted", declared=len(rels), written=written)
    return written
