"""Mock core-banking system of engagement (FR-26).

Deliberately a MOCK, and named as one. PRD section 8 excludes production
core-banking integration by design; what matters for the prototype is that the
action workflow calls a real HTTP surface, gets a real status code, and leaves a
real row behind - so the golden path proves something rather than simulating it.

Effects are persisted to SQLite. A mock that returns 200 and forgets would make
the audit trail (FR-9) a fiction, and the trail is the point: Aisha must be able
to reconstruct what happened from the database alone.

Idempotency is by `run_id` per instrument. A double-approve - a double-clicked
button, a retried request - must not credit an account twice. The second call
returns the first result and says so.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.engine import connect, query_all, query_one
from app.logging_setup import get_logger

log = get_logger("tools.core_banking")

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS cb_provisional_credits (
        credit_id      TEXT PRIMARY KEY,
        run_id         TEXT NOT NULL UNIQUE,
        created_at     TEXT NOT NULL,
        account_id     TEXT,
        customer_id    TEXT,
        transaction_id TEXT,
        amount         REAL NOT NULL,
        currency       TEXT NOT NULL DEFAULT 'USD',
        governing_clause TEXT,
        deadline       TEXT,
        status         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cb_dispute_cases (
        cb_case_id     TEXT PRIMARY KEY,
        run_id         TEXT NOT NULL UNIQUE,
        created_at     TEXT NOT NULL,
        customer_id    TEXT,
        transaction_id TEXT,
        reason_code    TEXT,
        queue          TEXT NOT NULL,
        amount         REAL,
        status         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cb_notices (
        notice_id   TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL UNIQUE,
        created_at  TEXT NOT NULL,
        customer_id TEXT,
        channel     TEXT NOT NULL,
        subject     TEXT,
        body        TEXT,
        status      TEXT NOT NULL
    )
    """,
]


def migrate() -> None:
    with connect() as conn:
        for statement in SCHEMA:
            conn.execute(statement)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def _existing(table: str, key: str, run_id: str) -> dict[str, Any] | None:
    return query_one(f"SELECT * FROM {table} WHERE run_id = ?", (run_id,))


def issue_provisional_credit(
    *,
    run_id: str,
    account_id: str | None,
    customer_id: str | None,
    transaction_id: str | None,
    amount: float,
    currency: str = "USD",
    governing_clause: str = "",
    deadline: str = "",
) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("provisional credit amount must be positive")

    prior = _existing("cb_provisional_credits", "credit_id", run_id)
    if prior:
        log.info("provisional_credit_idempotent", run_id=run_id, credit_id=prior["credit_id"])
        return dict(prior, idempotent=True)

    credit_id = _new_id("PC")
    row = {
        "credit_id": credit_id, "run_id": run_id, "created_at": _now(),
        "account_id": account_id, "customer_id": customer_id,
        "transaction_id": transaction_id, "amount": round(amount, 2),
        "currency": currency, "governing_clause": governing_clause,
        "deadline": deadline, "status": "posted",
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO cb_provisional_credits (credit_id, run_id, created_at, account_id, "
            "customer_id, transaction_id, amount, currency, governing_clause, deadline, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
    log.info("provisional_credit_posted", run_id=run_id, credit_id=credit_id, amount=amount)
    return dict(row, idempotent=False)


def open_dispute_case(
    *,
    run_id: str,
    customer_id: str | None,
    transaction_id: str | None,
    reason_code: str,
    queue: str,
    amount: float | None = None,
) -> dict[str, Any]:
    prior = _existing("cb_dispute_cases", "cb_case_id", run_id)
    if prior:
        log.info("dispute_case_idempotent", run_id=run_id, cb_case_id=prior["cb_case_id"])
        return dict(prior, idempotent=True)

    cb_case_id = _new_id("CASE")
    row = {
        "cb_case_id": cb_case_id, "run_id": run_id, "created_at": _now(),
        "customer_id": customer_id, "transaction_id": transaction_id,
        "reason_code": reason_code, "queue": queue, "amount": amount, "status": "open",
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO cb_dispute_cases (cb_case_id, run_id, created_at, customer_id, "
            "transaction_id, reason_code, queue, amount, status) VALUES (?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
    log.info("dispute_case_opened", run_id=run_id, cb_case_id=cb_case_id, queue=queue)
    return dict(row, idempotent=False)


def send_customer_notice(
    *,
    run_id: str,
    customer_id: str | None,
    subject: str,
    body: str,
    channel: str = "email",
) -> dict[str, Any]:
    prior = _existing("cb_notices", "notice_id", run_id)
    if prior:
        log.info("notice_idempotent", run_id=run_id, notice_id=prior["notice_id"])
        return dict(prior, idempotent=True)

    notice_id = _new_id("NTC")
    row = {
        "notice_id": notice_id, "run_id": run_id, "created_at": _now(),
        "customer_id": customer_id, "channel": channel, "subject": subject,
        "body": body, "status": "queued",
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO cb_notices (notice_id, run_id, created_at, customer_id, channel, "
            "subject, body, status) VALUES (?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
    log.info("notice_queued", run_id=run_id, notice_id=notice_id, customer_id=customer_id)
    return dict(row, idempotent=False)


def effects_for(run_id: str) -> dict[str, list[dict[str, Any]]]:
    """Everything this run touched. Backs the rejection assertion in acceptance
    criterion 7 - "no side effect" has to be checkable, not asserted."""
    return {
        "provisional_credits": query_all(
            "SELECT * FROM cb_provisional_credits WHERE run_id = ?", (run_id,)),
        "dispute_cases": query_all(
            "SELECT * FROM cb_dispute_cases WHERE run_id = ?", (run_id,)),
        "notices": query_all("SELECT * FROM cb_notices WHERE run_id = ?", (run_id,)),
    }
