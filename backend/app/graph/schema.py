"""Backend-neutral graph schema (PRD 5.5).

One declaration, two backends. Node and relationship shapes live here so the
Kuzu and Neo4j implementations cannot drift apart - a divergence between them
would be invisible until the fallback drill (acceptance criterion 9) failed.

Property types are declared because Kuzu requires typed DDL; Neo4j ignores them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NodeSpec:
    label: str
    key: str
    props: dict[str, str]           # name -> kuzu type
    display: str                    # property shown as the node caption


@dataclass(frozen=True)
class RelSpec:
    label: str
    src: str
    dst: str
    props: dict[str, str] = field(default_factory=dict)


NODES: tuple[NodeSpec, ...] = (
    NodeSpec("Customer", "customer_id", {
        "customer_id": "STRING", "name": "STRING", "product_tier": "STRING",
        "segment": "STRING", "since": "STRING", "email": "STRING",
    }, "name"),
    NodeSpec("Account", "account_id", {
        "account_id": "STRING", "product": "STRING", "opened": "STRING", "status": "STRING",
    }, "product"),
    NodeSpec("Merchant", "merchant_id", {
        "merchant_id": "STRING", "name": "STRING", "category": "STRING",
        "country": "STRING", "dispute_rate": "DOUBLE", "risk_band": "STRING",
    }, "name"),
    NodeSpec("Transaction", "transaction_id", {
        "transaction_id": "STRING", "amount": "DOUBLE", "currency": "STRING",
        "posted_at": "STRING", "channel": "STRING", "fraud_flag": "INT64",
        "fraud_score": "DOUBLE", "auth_code": "STRING", "status": "STRING",
    }, "transaction_id"),
    NodeSpec("Dispute", "dispute_id", {
        "dispute_id": "STRING", "transaction_id": "STRING", "reason_code": "STRING",
        "amount": "DOUBLE", "opened_at": "STRING", "outcome": "STRING",
    }, "reason_code"),
    NodeSpec("Policy", "clause_id", {
        "clause_id": "STRING", "doc_id": "STRING", "title": "STRING",
        "tier": "INT64", "tier_label": "STRING", "source_uri": "STRING",
    }, "clause_id"),
)

RELS: tuple[RelSpec, ...] = (
    RelSpec("HOLDS", "Customer", "Account"),
    RelSpec("MADE", "Account", "Transaction"),
    RelSpec("AT", "Transaction", "Merchant"),
    RelSpec("RAISED", "Customer", "Dispute"),
    # Policy-to-policy edges carry the rationale so the UI can explain WHY one
    # clause outranks another without a second lookup.
    RelSpec("SUPERSEDES", "Policy", "Policy", {"note": "STRING"}),
    RelSpec("REFERENCES", "Policy", "Policy", {"note": "STRING"}),
    RelSpec("DISTINCT_FROM", "Policy", "Policy", {"note": "STRING"}),
)

NODE_BY_LABEL = {n.label: n for n in NODES}
REL_BY_LABEL = {r.label: r for r in RELS}
POLICY_REL_LABELS = tuple(r.label for r in RELS if r.src == "Policy")


@dataclass
class NodeRow:
    label: str
    key: str
    props: dict[str, Any]


@dataclass
class RelRow:
    label: str
    src_key: str
    dst_key: str
    props: dict[str, Any] = field(default_factory=dict)


def coerce(label: str, props: dict[str, Any]) -> dict[str, Any]:
    """Fill declared properties and drop undeclared ones.

    Kuzu rejects an unknown column outright; Neo4j would silently accept it and
    the two graphs would no longer be the same graph. Normalising here keeps
    them identical.
    """
    spec = NODE_BY_LABEL[label]
    out: dict[str, Any] = {}
    for name, kind in spec.props.items():
        value = props.get(name)
        if value is None:
            out[name] = 0 if kind == "INT64" else (0.0 if kind == "DOUBLE" else "")
        elif kind == "INT64":
            out[name] = int(value)
        elif kind == "DOUBLE":
            out[name] = float(value)
        else:
            out[name] = str(value)
    return out
