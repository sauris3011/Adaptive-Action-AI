"""Authoritative entity state in SQLite (PRD 5.5, third grounding source).

This is where the **fraud flag** lives. It exists in no policy document, which
is the whole point of conflict C3: a documents-only system cannot resolve it at
all. The graph mirrors these facts for traversal; this table is the record of
truth, and `transaction_facts` is what the reconciler is grounded on.

Queries return typed Evidence, so relational facts and policy passages enter the
GroundingContext through the same door.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.db.engine import connect, query_all, query_one
from app.logging_setup import get_logger
from app.schemas.grounding import Evidence, EvidenceKind

log = get_logger("db.records")

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id  TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        product_tier TEXT NOT NULL,
        segment      TEXT,
        since        TEXT,
        email        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        account_id  TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        product     TEXT,
        opened      TEXT,
        status      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS merchants (
        merchant_id  TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        category     TEXT,
        country      TEXT,
        dispute_rate REAL,
        risk_band    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id TEXT PRIMARY KEY,
        account_id     TEXT NOT NULL,
        customer_id    TEXT NOT NULL,
        merchant_id    TEXT NOT NULL,
        amount         REAL NOT NULL,
        currency       TEXT NOT NULL DEFAULT 'USD',
        posted_at      TEXT,
        channel        TEXT,
        -- The field no document contains. C3 turns on this column.
        fraud_flag     INTEGER NOT NULL DEFAULT 0,
        fraud_score    REAL    NOT NULL DEFAULT 0.0,
        auth_code      TEXT,
        status         TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_txn_customer ON transactions(customer_id)",
    """
    CREATE TABLE IF NOT EXISTS dispute_history (
        dispute_id     TEXT PRIMARY KEY,
        customer_id    TEXT NOT NULL,
        transaction_id TEXT,
        reason_code    TEXT,
        amount         REAL,
        opened_at      TEXT,
        outcome        TEXT
    )
    """,
]

_TABLES = ("customers", "accounts", "merchants", "transactions", "dispute_history")


# Columns added after the first release. CREATE TABLE IF NOT EXISTS is a no-op
# on a database that already has the table, so a new column needs its own step.
_ADDITIONS: tuple[tuple[str, str, str], ...] = (
    ("dispute_history", "run_id", "TEXT"),
)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Additive migration, checked rather than caught.

    Wrapping ALTER TABLE in a bare except would also swallow a genuinely broken
    migration; reading the table definition says what is actually true.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    log.info("column_added", table=table, column=column)


def migrate() -> None:
    with connect() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        for table, column, decl in _ADDITIONS:
            _add_column_if_missing(conn, table, column, decl)


def load(records: dict[str, Any]) -> dict[str, int]:
    """Idempotent fixture load. REPLACE rather than IGNORE so a corrected
    fixture actually takes effect on re-seed."""
    counts: dict[str, int] = {}
    inserts = {
        "customers": ("customers", ["customer_id", "name", "product_tier", "segment",
                                    "since", "email"]),
        "accounts": ("accounts", ["account_id", "customer_id", "product", "opened", "status"]),
        "merchants": ("merchants", ["merchant_id", "name", "category", "country",
                                    "dispute_rate", "risk_band"]),
        "transactions": ("transactions", ["transaction_id", "account_id", "customer_id",
                                          "merchant_id", "amount", "currency", "posted_at",
                                          "channel", "fraud_flag", "fraud_score",
                                          "auth_code", "status"]),
        "disputes": ("dispute_history", ["dispute_id", "customer_id", "transaction_id",
                                         "reason_code", "amount", "opened_at", "outcome"]),
    }
    with connect() as conn:
        for key, (table, columns) in inserts.items():
            rows = records.get(key, [])
            placeholders = ",".join("?" * len(columns))
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                [tuple(row.get(c) for c in columns) for row in rows],
            )
            counts[table] = len(rows)
    log.info("records_loaded", **counts)
    return counts


def clear() -> None:
    with connect() as conn:
        for table in _TABLES:
            conn.execute(f"DELETE FROM {table}")


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def get_transaction(transaction_id: str) -> dict[str, Any] | None:
    return query_one(
        "SELECT t.*, c.name AS customer_name, c.product_tier, c.since AS customer_since, "
        "a.opened AS account_opened, m.name AS merchant_name, m.risk_band, m.dispute_rate "
        "FROM transactions t "
        "JOIN customers c ON c.customer_id = t.customer_id "
        "JOIN accounts  a ON a.account_id  = t.account_id "
        "JOIN merchants m ON m.merchant_id = t.merchant_id "
        "WHERE t.transaction_id = ?",
        (transaction_id,),
    )


def get_customer(customer_id: str) -> dict[str, Any] | None:
    return query_one("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))


def find_transactions(customer_id: str, limit: int = 10) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM transactions WHERE customer_id = ? ORDER BY posted_at DESC LIMIT ?",
        (customer_id, limit),
    )


def transaction_facts(transaction_id: str) -> Evidence | None:
    """The relational half of hybrid grounding, rendered for the prompt.

    The fraud flag is stated in words rather than as a raw 0/1, because the
    reconciler must be able to act on it without inferring a column convention.
    """
    row = get_transaction(transaction_id)
    if row is None:
        return None

    flagged = bool(row["fraud_flag"])
    lines = [
        f"Transaction {row['transaction_id']}: {row['amount']:.2f} {row['currency']} "
        f"at {row['merchant_name']} ({row['merchant_id']}) on {row['posted_at']}.",
        f"Channel: {row['channel']}. Status: {row['status']}.",
        f"Fraud-engine flag: {'PRESENT' if flagged else 'absent'} "
        f"(score {row['fraud_score']:.2f}).",
        f"Cardholder: {row['customer_name']} ({row['customer_id']}), "
        f"product tier {row['product_tier']}, customer since {row['customer_since']}.",
        f"Account {row['account_id']} opened {row['account_opened']}.",
        f"Merchant risk band: {row['risk_band']} "
        f"(dispute rate {row['dispute_rate']:.3f}).",
    ]
    return Evidence(
        kind=EvidenceKind.RECORD,
        ref=f"REC:{row['transaction_id']}",
        title="Transaction record (system of record)",
        content="\n".join(lines),
    )


def counts() -> dict[str, int]:
    with connect() as conn:
        return {t: conn.execute(f"SELECT count(*) AS c FROM {t}").fetchone()["c"]
                for t in _TABLES}


# --------------------------------------------------------------------------
# Disputes
#
# `dispute_history` was a seed-only table: written by load(), read by nothing.
# The graph's Dispute nodes were the only copy anything queried, which made the
# fixture - not the record - the source of dispute history. These functions make
# this table the record and leave the graph a projection of it, so a dispute
# raised at runtime is visible to retrieval the way a seeded one always was.
# --------------------------------------------------------------------------

OPEN = "open"

_DISPUTE_COLUMNS = ("dispute_id", "customer_id", "transaction_id", "reason_code",
                    "amount", "opened_at", "outcome", "run_id")

# Deterministic, like the action mapping in agents/actions.py. What a decision
# means for the record is a policy question, not one the model gets to answer.
_APPROVED_OUTCOMES = {
    "provisional_credit": "resolved_credit",
    "goodwill_refund": "goodwill_refund",
    "route_to_fraud_ops": "routed_to_fraud_ops",
    "request_merchant_contact": "awaiting_merchant_contact",
}


def outcome_for(case_outcome: str | None, action: str | None) -> str:
    """Map a closed run onto the dispute vocabulary the fixture already uses.

    `case_outcome` is what record_node computed for the case row, so the two
    cannot disagree about whether the actions actually succeeded.
    """
    if case_outcome == "rejected":
        return "rejected"
    if case_outcome == "approved_action_failed":
        return "action_failed"
    if case_outcome == "approved":
        return _APPROVED_OUTCOMES.get(action or "", "resolved")
    return OPEN


def open_dispute(
    *,
    run_id: str,
    customer_id: str,
    transaction_id: str,
    reason_code: str | None = None,
    amount: float | None = None,
) -> dict[str, Any]:
    """Record an intake. Idempotent per transaction, not per run.

    A second run against a transaction that already has an open dispute attaches
    to the existing one rather than creating a rival. Per-run idempotency is what
    the core-banking mock does, and it is exactly what fails to stop the same
    transaction being disputed twice under two different run ids.
    """
    existing = query_one(
        "SELECT * FROM dispute_history WHERE transaction_id = ? AND outcome = ? "
        "ORDER BY opened_at DESC LIMIT 1",
        (transaction_id, OPEN),
    )
    if existing:
        log.info("dispute_intake_reused", dispute_id=existing["dispute_id"],
                 transaction_id=transaction_id, run_id=run_id)
        return dict(existing, reused=True)

    row = {
        "dispute_id": f"DSP-{run_id.removeprefix('run-').upper()}",
        "customer_id": customer_id,
        "transaction_id": transaction_id,
        "reason_code": reason_code,
        "amount": float(amount) if amount is not None else None,
        # A date, not a timestamp: the column holds dates in the fixture and the
        # graph sorts dispute history on it lexically.
        "opened_at": datetime.now(timezone.utc).date().isoformat(),
        "outcome": OPEN,
        "run_id": run_id,
    }
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO dispute_history ({','.join(_DISPUTE_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(_DISPUTE_COLUMNS))})",
            tuple(row[c] for c in _DISPUTE_COLUMNS),
        )
    log.info("dispute_opened", dispute_id=row["dispute_id"], run_id=run_id,
             transaction_id=transaction_id, customer_id=customer_id)
    return dict(row, reused=False)


def set_dispute_outcome(
    *, dispute_id: str, outcome: str, run_id: str | None = None
) -> dict[str, Any] | None:
    """Close an OPEN dispute, stamping the run that decided it.

    First decision wins. Two runs can share one dispute - the second attached to
    it rather than opening a rival - and they can be decided differently: the
    first approved and credited, the second rejected. Letting the later decision
    overwrite would leave the record saying "rejected" about a transaction that
    demonstrably carries a credit.

    The first decision is also the only one whose effects reached the ledger,
    because `issue_provisional_credit` refuses a second credit on the same
    transaction. So the rule keeps the summary and the ledger telling the same
    story. Every run still records its own outcome in its case row and its
    trace; this column summarises the dispute, not the run.
    """
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE dispute_history SET outcome = ?, run_id = coalesce(?, run_id) "
            "WHERE dispute_id = ? AND outcome = ?",
            (outcome, run_id, dispute_id, OPEN))
        updated = cursor.rowcount

    row = query_one("SELECT * FROM dispute_history WHERE dispute_id = ?", (dispute_id,))
    if row is None:
        log.warning("dispute_outcome_missing", dispute_id=dispute_id, outcome=outcome)
        return None
    if not updated:
        log.info("dispute_outcome_already_recorded", dispute_id=dispute_id,
                 standing=row["outcome"], declined=outcome, run_id=run_id)
        return row
    log.info("dispute_outcome_set", dispute_id=dispute_id, outcome=outcome, run_id=run_id)
    return row


def all_disputes() -> list[dict[str, Any]]:
    """Every dispute, fixture and runtime alike. The graph projects from here."""
    return query_all("SELECT * FROM dispute_history ORDER BY opened_at")


def disputes_for_customer(customer_id: str) -> list[dict[str, Any]]:
    return query_all(
        "SELECT * FROM dispute_history WHERE customer_id = ? ORDER BY opened_at DESC",
        (customer_id,),
    )


def open_dispute_for_transaction(transaction_id: str) -> dict[str, Any] | None:
    return query_one(
        "SELECT * FROM dispute_history WHERE transaction_id = ? AND outcome = ?",
        (transaction_id, OPEN),
    )


def dispute_map() -> dict[str, dict[str, Any]]:
    """transaction_id -> the dispute that governs that look-up row.

    An open dispute always outranks a closed one: the screen's job is to stop a
    second intake on something already in flight, and a dispute resolved last
    year must not mask one opened this morning.
    """
    rows = query_all(
        "SELECT * FROM dispute_history WHERE transaction_id IS NOT NULL "
        "ORDER BY (outcome = ?) DESC, opened_at DESC",
        (OPEN,),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out.setdefault(row["transaction_id"], row)
    return out
