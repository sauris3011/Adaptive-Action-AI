"""Plain-language questions resolved onto the fixed five-query surface (FR-15).

The surface is five audited methods rather than a Cypher passthrough, because
the Kuzu fallback dialect diverges from Neo4j exactly where a free-form query
would live - a passthrough would make the second backend unaffordable to keep.
This module is the part the UI makes visible: it picks one of the five, names
the call it picked, and hands back both the answer and the neighbourhood.

Resolution is keyword matching, not a model call. Three reasons: the answer must
be reproducible when a team lead re-runs it, the screen must work with the
gateway disabled (PRD 5.8), and a wrong resolution is recoverable by tapping a
different chip - which only works if the mapping is something a human can
predict.

Answers are composed from the rows the store actually returned. Nothing on this
screen is generated prose.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.graph.base import active_backend, get_store

METHODS = (
    "merchant_risk_profile",
    "customer_dispute_history",
    "transaction_context",
    "policy_dependencies",
    "neighborhood",
)

# Served to the UI so the rail's "five queries" list cannot drift from the
# GraphStore protocol it is describing.
SURFACE: list[dict[str, str]] = [
    {"id": "merchant_risk_profile",
     "description": "Dispute rate, risk band and transaction volume for one merchant."},
    {"id": "customer_dispute_history",
     "description": "Every dispute a cardholder has raised, with outcomes."},
    {"id": "transaction_context",
     "description": "Customer to account to transaction to merchant, plus the fraud flag."},
    {"id": "policy_dependencies",
     "description": "Which clauses supersede or reference which."},
    {"id": "neighborhood",
     "description": "Generic n-hop expansion from any entity."},
]

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("merchant_risk_profile",
     ("merchant", "seller", "retailer", "risk band", "dispute rate", "anyone else")),
    ("customer_dispute_history",
     ("cardholder", "customer", "history", "raised", "disputed before", "past disputes",
      "repeat")),
    ("transaction_context",
     ("transaction", "txn", "trace", "context", "fraud flag", "authorisation", "authorization")),
    ("policy_dependencies",
     ("policy", "clause", "supersede", "supersedes", "reference", "governs", "rule")),
    ("neighborhood",
     ("neighbour", "neighbor", "connected", "related", "expand", "around", "hops")),
]

_ID_PATTERNS: list[tuple[str, str]] = [
    (r"\bTXN-\d+\b", "transaction_context"),
    (r"\bCUST-\d+\b", "customer_dispute_history"),
    (r"\bMERCH-\d+\b", "merchant_risk_profile"),
    (r"\bDSP-\d+\b", "neighborhood"),
    (r"\bACC-\d+\b", "neighborhood"),
    # Policy clauses are the only ids carrying a dotted section number.
    (r"\b[A-Z]{2,4}(?:-[A-Z])?-\d+(?:\.\d+)?\b", "policy_dependencies"),
]

_BAND_TONE: dict[str, str] = {"high": "danger", "elevated": "warning", "low": "success"}
_OUTCOME_TONE: dict[str, str] = {
    "resolved_credit": "success", "goodwill_refund": "success",
    "rejected": "warning", "open": "info",
}


# ---------------------------------------------------------------------------
# Entity binding
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _captions(backend: str, label: str) -> tuple[tuple[str, str], ...]:
    """(key, caption) pairs for one label.

    Cached per backend: the seed set is static within a run, and the fallback
    drill changes the cache key rather than needing an explicit invalidation.
    """
    store = get_store()
    found: list[tuple[str, str]] = []
    for key in store.keys(label):
        node = store.node_by_key(key)
        if node:
            found.append((key, node["caption"]))
    return tuple(found)


@lru_cache(maxsize=8)
def _defaults(backend: str) -> dict[str, str]:
    """The entity each method falls back to when the question names none.

    Chosen from the data rather than hardcoded, so a re-seeded domain pack still
    lands on the row worth looking at: the riskiest merchant, the most-disputed
    cardholder, a flagged transaction, the clause with the most dependencies.
    """
    store = get_store()
    out: dict[str, str] = {}

    merchants = [profile for profile in
                 (store.merchant_risk_profile(k) for k in store.keys("Merchant")) if profile]
    if merchants:
        out["merchant_risk_profile"] = max(
            merchants, key=lambda m: m.get("dispute_rate") or 0.0)["merchant_id"]

    customers = [(k, len(store.customer_dispute_history(k))) for k in store.keys("Customer")]
    if customers:
        out["customer_dispute_history"] = max(customers, key=lambda pair: pair[1])[0]

    transactions = [ctx for ctx in
                    (store.transaction_context(k) for k in store.keys("Transaction")) if ctx]
    if transactions:
        flagged = [t for t in transactions if t.get("fraud_flag")]
        out["transaction_context"] = (flagged or transactions)[0]["transaction_id"]
        out["neighborhood"] = out["transaction_context"]

    clauses = [(k, len(store.policy_dependencies(k))) for k in store.keys("Policy")]
    if clauses:
        out["policy_dependencies"] = max(clauses, key=lambda pair: pair[1])[0]

    return out


def _method_from_name(question: str) -> str | None:
    """Naming an entity is itself a signal about which query is wanted.

    "What has R. Okafor disputed before?" carries none of the keywords but is
    unambiguously a history question, because the thing it names is a cardholder.
    """
    lowered = question.lower()
    backend = active_backend()
    for label, method in (("Merchant", "merchant_risk_profile"),
                          ("Customer", "customer_dispute_history")):
        for _key, caption in _captions(backend, label):
            if caption and caption.lower() in lowered:
                return method
    return None


def _bind(question: str, method: str) -> str | None:
    """Pull an entity out of the question: an explicit id first, then a name."""
    upper = question.upper()
    for pattern, _implied in _ID_PATTERNS:
        found = re.search(pattern, upper)
        if found:
            return found.group(0)

    backend = active_backend()
    lowered = question.lower()
    for label in ("Merchant", "Customer"):
        for key, caption in _captions(backend, label):
            if caption and caption.lower() in lowered:
                return key
    return _defaults(backend).get(method)


def resolve(question: str, method: str | None = None) -> dict[str, Any]:
    """Question to one of the five, plus the entity it will run against.

    An explicit `method` (a chip tap) wins over the keywords: that is the
    recovery path for when resolution guessed wrong, and it is the reason the
    resolved call is always on screen.
    """
    text = question.strip()
    lowered = text.lower()

    picked = method if method in METHODS else None
    if picked is None:
        for pattern, implied in _ID_PATTERNS:
            if re.search(pattern, text.upper()):
                picked = implied
                break
    if picked is None:
        for candidate, words in _KEYWORDS:
            if any(word in lowered for word in words):
                picked = candidate
                break

    if picked is None:
        picked = _method_from_name(text)

    picked = picked or "neighborhood"
    return {"method": picked, "entity": _bind(text, picked)}


# ---------------------------------------------------------------------------
# Answers, composed from the rows the store returned
# ---------------------------------------------------------------------------

def _pct(value: float | None) -> str:
    return f"{(value or 0.0) * 100:.1f}%"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _merchant_answer(profile: dict[str, Any] | None) -> tuple[str, list[dict[str, str]]]:
    if not profile:
        return "That merchant is not in the graph.", []

    band = (profile.get("risk_band") or "unknown").lower()
    rate = profile.get("dispute_rate")
    count = int(profile.get("transaction_count") or 0)
    tone = _BAND_TONE.get(band, "neutral")
    text = (
        f"{profile['name']} carries a {_pct(rate)} dispute rate across "
        f"{_plural(count, 'transaction')} in the record, which puts it in the {band} "
        f"risk band. Risk band is a merchant-level fact held on the record, so it is "
        f"available before any document is retrieved."
    )
    return text, [
        {"label": f"{_pct(rate)} DISPUTE RATE", "tone": tone},
        {"label": _plural(count, "TRANSACTION").upper(), "tone": "neutral"},
        {"label": f"RISK BAND {band.upper()}", "tone": tone},
    ]


def _history_answer(name: str, rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    if not rows:
        return (
            f"{name} has raised no disputes in the record. Nothing in their history "
            f"weakens or supports the current case.",
            [{"label": "0 DISPUTES", "tone": "success"}],
        )

    outcomes: dict[str, int] = {}
    for row in rows:
        key = row.get("outcome") or "open"
        outcomes[key] = outcomes.get(key, 0) + 1
    reasons = sorted({(row.get("reason_code") or "unknown") for row in rows})

    summary = ", ".join(f"{n} {key.replace('_', ' ')}" for key, n in outcomes.items())
    text = (
        f"{name} has raised {_plural(len(rows), 'dispute')} in the record ({summary}). "
        f"Reason codes seen: {', '.join(r.replace('_', ' ') for r in reasons)}."
    )
    tags = [{"label": _plural(len(rows), "DISPUTE").upper(), "tone": "neutral"}]
    tags += [
        {"label": f"{n} {key.replace('_', ' ').upper()}", "tone": _OUTCOME_TONE.get(key, "info")}
        for key, n in outcomes.items()
    ]
    return text, tags


def _context_answer(ctx: dict[str, Any] | None) -> tuple[str, list[dict[str, str]]]:
    if not ctx:
        return "That transaction is not in the graph.", []

    flagged = bool(ctx.get("fraud_flag"))
    flag_sentence = (
        f"It carries a fraud-engine flag scored {float(ctx.get('fraud_score') or 0):.2f}, "
        f"attached at authorisation - that flag is the deciding input for routing and it "
        f"exists only on the record."
        if flagged
        else "No fraud-engine flag is attached, so standard dispute intake applies."
    )
    text = (
        f"{ctx['transaction_id']} traces from {ctx.get('customer_name')} "
        f"({ctx.get('product_tier')}) through account {ctx.get('account_id')} to "
        f"{ctx.get('merchant_name')}: {float(ctx.get('amount') or 0):.2f} "
        f"{ctx.get('currency')} on {ctx.get('posted_at')} over {ctx.get('channel')}. "
        f"{flag_sentence}"
    )
    band = (ctx.get("merchant_risk_band") or "unknown").lower()
    return text, [
        {"label": "FRAUD FLAG PRESENT" if flagged else "NO FRAUD FLAG",
         "tone": "danger" if flagged else "success"},
        {"label": f"MERCHANT {band.upper()}", "tone": _BAND_TONE.get(band, "neutral")},
        {"label": f"CHANNEL {str(ctx.get('channel') or 'unknown').upper()}", "tone": "neutral"},
    ]


def _policy_answer(clause: str, rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    if not rows:
        return (
            f"{clause} has no recorded dependencies - it neither supersedes nor references "
            f"another clause in the pack.",
            [{"label": "0 EDGES", "tone": "neutral"}],
        )

    outgoing = [r for r in rows if r.get("direction") == "outgoing"]
    incoming = [r for r in rows if r.get("direction") == "incoming"]
    supersedes = [r["clause_id"] for r in outgoing if r.get("relation") == "SUPERSEDES"]
    references = [r["clause_id"] for r in outgoing if r.get("relation") == "REFERENCES"]

    parts: list[str] = []
    if supersedes:
        parts.append(f"supersedes {', '.join(supersedes)}")
    if references:
        parts.append(f"references {', '.join(references)}")
    if incoming:
        parts.append(f"is pointed at by {', '.join(sorted({r['clause_id'] for r in incoming}))}")

    related = {r["clause_id"] for r in rows}
    tiers = sorted({r["tier"] for r in rows if r.get("tier") is not None})
    tier_list = ", ".join(str(t) for t in tiers)
    text = (
        f"{clause} {'; '.join(parts) if parts else 'has dependencies in the pack'}. "
        f"{_plural(len(related), 'other clause')} form the governing set, spanning "
        f"tier{'' if len(tiers) == 1 else 's'} {tier_list or 'n/a'}."
    )
    return text, [
        {"label": _plural(len(rows), "EDGE").upper(), "tone": "neutral"},
        {"label": f"{len(supersedes)} SUPERSEDES", "tone": "info" if supersedes else "neutral"},
        {"label": f"TIERS {tier_list or 'N/A'}", "tone": "info"},
    ]


def _neighborhood_answer(entity: str, view: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if not view.get("found"):
        return (f"No node in the graph has the key {entity}.",
                [{"label": "NOT FOUND", "tone": "warning"}])

    labels: dict[str, int] = {}
    for node in view["nodes"]:
        labels[node["label"]] = labels.get(node["label"], 0) + 1
    breakdown = ", ".join(_plural(n, key.lower()) for key, n in sorted(labels.items()))

    hops = view.get("hops")
    text = (
        f"Expanding from {entity} reaches {len(view['nodes'])} entities within "
        f"{_plural(int(hops or 0), 'hop')}: {breakdown}."
    )
    tags = [{"label": f"{len(view['nodes'])} ENTITIES", "tone": "neutral"},
            {"label": f"{len(view['links'])} RELATIONSHIPS", "tone": "neutral"}]
    if view.get("truncated"):
        tags.append({"label": "TRUNCATED AT CAP", "tone": "warning"})
    return text, tags


# ---------------------------------------------------------------------------

def _empty(question: str, method: str, hops: int) -> dict[str, Any]:
    return {
        "question": question,
        "resolved": {"method": method, "entity": None, "display": f"{method}(no entity)"},
        "answer": "Nothing in the question names an entity this graph holds, and no default "
                  "could be drawn from the store. Seed the domain pack to populate it.",
        "tags": [{"label": "NO ENTITY", "tone": "warning"}],
        "view": {"root": None, "found": False, "hops": hops, "nodes": [], "links": [],
                 "truncated": False},
        "backend": active_backend(),
        "hops": hops,
        "surface": SURFACE,
    }


def ask(question: str, hops: int = 2, method: str | None = None) -> dict[str, Any]:
    """Resolve, run, and return the answer with its corroborating neighbourhood.

    The neighbourhood always accompanies the sentence rather than replacing it:
    the sentence is the deliverable, the picture is what an agent points a team
    lead at when the sentence is challenged.
    """
    store = get_store()
    resolution = resolve(question, method)
    picked, entity = resolution["method"], resolution["entity"]
    if entity is None:
        return _empty(question, picked, hops)

    view = store.neighborhood(entity, hops)
    node = store.node_by_key(entity)
    caption = node["caption"] if node else entity

    if picked == "merchant_risk_profile":
        answer, tags = _merchant_answer(store.merchant_risk_profile(entity))
        display = f"merchant_risk_profile({caption})"
    elif picked == "customer_dispute_history":
        answer, tags = _history_answer(caption, store.customer_dispute_history(entity))
        display = f"customer_dispute_history({caption})"
    elif picked == "transaction_context":
        answer, tags = _context_answer(store.transaction_context(entity))
        display = f"transaction_context({entity})"
    elif picked == "policy_dependencies":
        answer, tags = _policy_answer(entity, store.policy_dependencies(entity))
        display = f"policy_dependencies({entity})"
    else:
        answer, tags = _neighborhood_answer(entity, view)
        display = f"neighborhood({entity}, {_plural(hops, 'hop')})"

    return {
        "question": question,
        "resolved": {"method": picked, "entity": entity, "display": display},
        "answer": answer,
        "tags": tags,
        "view": view,
        "backend": active_backend(),
        "hops": hops,
        "surface": SURFACE,
    }
