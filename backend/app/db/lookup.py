"""Transaction look-up over the authoritative record (FR-2, structured half).

The look-up screen's whole claim is that the signals it shows were computed on
the record rather than produced by a model. That claim only holds if the
derivation lives here, on the server, next to the table it reads - so `fraud`,
`duplicate` and `disputed` are resolved in this module and travel to the UI as
facts.

`duplicate` is deliberately computed over the *whole* table rather than the
filtered view: a duplicate's partner may sit outside the selected window, and a
signal that flickers as the operator changes scope is worse than no signal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from app.db import records
from app.db.engine import query_all

Scope = Literal["30d", "90d", "all"]

# Same merchant, same amount, this far apart or less.
DUPLICATE_WINDOW_DAYS = 7

_SCOPE_DAYS: dict[str, int | None] = {"30d": 30, "90d": 90, "all": None}

_SELECT = (
    "SELECT t.transaction_id, t.account_id, t.customer_id, t.merchant_id, "
    "t.amount, t.currency, t.posted_at, t.channel, t.fraud_flag, t.fraud_score, "
    "t.auth_code, t.status, "
    "c.name AS customer_name, c.product_tier, "
    "m.name AS merchant_name, m.category AS merchant_category, "
    "m.country AS merchant_country, m.dispute_rate, m.risk_band "
    "FROM transactions t "
    "JOIN customers c ON c.customer_id = t.customer_id "
    "JOIN merchants m ON m.merchant_id = t.merchant_id "
    "ORDER BY t.posted_at DESC"
)


def _parse(posted_at: str | None) -> date | None:
    if not posted_at:
        return None
    try:
        return datetime.fromisoformat(posted_at[:10]).date()
    except ValueError:
        return None


def _card_last4(account_id: str | None) -> str:
    """The card number is not in the record; the account is.

    Operators search by the last four digits they can read off a statement, so
    the account tail stands in for it rather than inventing a PAN we do not hold.
    """
    digits = "".join(ch for ch in (account_id or "") if ch.isdigit())
    return digits[-4:]


def _signal(row: dict[str, Any], duplicate_of: str | None, disputed: bool) -> str | None:
    """Precedence matches the row styling: fraud outranks everything.

    `disputed` sits second rather than first deliberately. A fraud-flagged
    transaction that has also been disputed still routes on the fraud flag under
    FSP-1.2, and letting an open dispute mask that would hide the one fact
    conflict C3 turns on.
    """
    if row["fraud_flag"]:
        return "fraud"
    if disputed:
        return "disputed"
    if duplicate_of:
        return "duplicate"
    if (row["status"] or "").lower() in {"reversed", "reversal"}:
        return "reversed"
    return None


def _duplicates(rows: list[dict[str, Any]]) -> dict[str, str]:
    """transaction_id -> the id of the transaction it duplicates.

    O(n^2) over a table this size is not worth indexing around, and the pairwise
    form keeps the rule ("same merchant, same amount, within 7 days") readable
    as the sentence the footnote promises the operator.
    """
    found: dict[str, str] = {}
    window = timedelta(days=DUPLICATE_WINDOW_DAYS)
    for i, a in enumerate(rows):
        day_a = _parse(a["posted_at"])
        if day_a is None:
            continue
        for b in rows[i + 1:]:
            day_b = _parse(b["posted_at"])
            if day_b is None:
                continue
            if (
                a["merchant_id"] == b["merchant_id"]
                and abs(a["amount"] - b["amount"]) < 0.005
                and abs(day_a - day_b) <= window
            ):
                found.setdefault(a["transaction_id"], b["transaction_id"])
                found.setdefault(b["transaction_id"], a["transaction_id"])
    return found


def _matches(row: dict[str, Any], q: str) -> bool:
    """Reference, merchant and date match on substring; amount and card tail
    match after punctuation is stripped, so a value pasted straight out of the
    look-up placeholder (`····4429`) still finds its row."""
    if not q:
        return True
    needle = q.strip().lower()
    if not needle:
        return True
    compact = "".join(ch for ch in needle if ch.isalnum() or ch == ".")

    haystack = [
        row["transaction_id"].lower(),
        (row["merchant_name"] or "").lower(),
        (row["posted_at"] or "").lower(),
        row["date_label"].lower(),
        (row["customer_name"] or "").lower(),
    ]
    if any(needle in field for field in haystack):
        return True
    return bool(compact) and (
        compact in f"{row['amount']:.2f}" or compact in row["card_last4"]
    )


def _decorate(
    row: dict[str, Any],
    duplicate_of: str | None,
    dispute: dict[str, Any] | None,
) -> dict[str, Any]:
    day = _parse(row["posted_at"])
    disputed = bool(dispute and dispute["outcome"] == records.OPEN)
    return dict(
        row,
        fraud_flag=bool(row["fraud_flag"]),
        date_label=day.strftime("%d %b") if day else (row["posted_at"] or ""),
        card_last4=_card_last4(row["account_id"]),
        duplicate_of=duplicate_of,
        dispute_id=dispute["dispute_id"] if dispute else None,
        dispute_outcome=dispute["outcome"] if dispute else None,
        # The run that raised it, so the screen can hand the operator back to
        # the gate it is parked at. Null for the seeded fixture disputes, which
        # never had a run.
        dispute_run_id=dispute["run_id"] if dispute else None,
        # Only an OPEN dispute blocks a second intake. A resolved one is history
        # worth showing, not a reason to refuse the operator.
        disputed=disputed,
        signal=_signal(row, duplicate_of, disputed),
    )


def search(q: str = "", scope: Scope = "30d") -> dict[str, Any]:
    """Everything the look-up screen renders, in one round trip.

    The window is anchored on the newest posted transaction rather than on the
    wall clock: the domain pack is a fixture with fixed dates, and a scope
    control that silently empties as the fixture ages would read as a bug in the
    query rather than as staleness in the data. `as_of` is returned so the UI can
    say which day "last 30 days" is counted back from.
    """
    rows = query_all(_SELECT, ())
    duplicate_map = _duplicates(rows)
    disputes = records.dispute_map()
    decorated = [
        _decorate(row, duplicate_map.get(row["transaction_id"]),
                  disputes.get(row["transaction_id"]))
        for row in rows
    ]

    days = _SCOPE_DAYS.get(scope, 30)
    dated = [d for d in (_parse(r["posted_at"]) for r in decorated) if d is not None]
    as_of = max(dated) if dated else date.today()

    in_scope = decorated
    if days is not None:
        floor = as_of - timedelta(days=days)
        in_scope = [r for r in decorated if (_parse(r["posted_at"]) or as_of) >= floor]

    matched = [r for r in in_scope if _matches(r, q)]
    return {
        "query": q,
        "scope": scope,
        "as_of": as_of.isoformat(),
        "count": len(matched),
        "total": len(decorated),
        "transactions": matched,
    }


def get(transaction_id: str) -> dict[str, Any] | None:
    """One decorated row, with the duplicate signal resolved the same way."""
    rows = query_all(_SELECT, ())
    duplicate_map = _duplicates(rows)
    for row in rows:
        if row["transaction_id"] == transaction_id:
            return _decorate(row, duplicate_map.get(transaction_id),
                             records.dispute_map().get(transaction_id))
    return None
