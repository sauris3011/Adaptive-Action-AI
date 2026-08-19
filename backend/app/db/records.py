"""Authoritative entity state in SQLite (PRD 5.5, third grounding source).

This is where the **fraud flag** lives. It exists in no policy document, which
is the whole point of conflict C3: a documents-only system cannot resolve it at
all. The graph mirrors these facts for traversal; this table is the record of
truth, and `transaction_facts` is what the reconciler is grounded on.

Queries return typed Evidence, so relational facts and policy passages enter the
GroundingContext through the same door.
"""

from __future__ import annotations

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


def migrate() -> None:
    with connect() as conn:
        for statement in SCHEMA:
            conn.execute(statement)


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
