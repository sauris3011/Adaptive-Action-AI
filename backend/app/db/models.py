"""Schema DDL and migration.

Idempotent: safe to run on every boot. LangGraph's SqliteSaver manages its own
checkpoint tables in the same file and is not declared here.
"""

from __future__ import annotations

from app.db.engine import connect

SCHEMA = [
    # --- Telemetry ledger: the source of truth for the header monitor -------
    # Deliberately local rather than a round trip to LiteLLM /spend or
    # LangSmith, because an always-visible UI element must not depend on a SaaS
    # hop through a TLS-intercepting proxy (PRD 5.8).
    """
    CREATE TABLE IF NOT EXISTS llm_calls (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        ts                TEXT    NOT NULL,
        run_id            TEXT,
        node              TEXT,
        call_class        TEXT    NOT NULL,
        exemption_reason  TEXT,
        model             TEXT    NOT NULL,
        prompt_tokens     INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens      INTEGER NOT NULL DEFAULT 0,
        cost_usd          REAL    NOT NULL DEFAULT 0.0,
        latency_ms        INTEGER NOT NULL DEFAULT 0,
        cache_hit         INTEGER NOT NULL DEFAULT 0,
        error             TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls(ts)",
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_run ON llm_calls(run_id)",

    # --- Prompt cache -------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS llm_cache (
        cache_key   TEXT PRIMARY KEY,
        model       TEXT NOT NULL,
        response    TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        hits        INTEGER NOT NULL DEFAULT 0
    )
    """,

    # --- Audit trail: every decision reconstructable from SQLite alone ------
    """
    CREATE TABLE IF NOT EXISTS run_events (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id    TEXT NOT NULL,
        ts        TEXT NOT NULL,
        node      TEXT NOT NULL,
        event     TEXT NOT NULL,
        payload   TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id)",

    # --- Dispute cases ------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS dispute_cases (
        case_id        TEXT PRIMARY KEY,
        run_id         TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        customer_id    TEXT,
        transaction_id TEXT,
        reason_code    TEXT,
        recommendation TEXT,
        governing_clause TEXT,
        confidence     REAL,
        outcome        TEXT NOT NULL,
        approver       TEXT,
        approved_at    TEXT,
        reject_reason  TEXT,
        elapsed_ms     INTEGER
    )
    """,
]


def migrate() -> None:
    from app.db import records
    from app.tools import core_banking

    with connect() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
    # Entity state lives in its own module (app/db/records.py) to keep this file
    # focused on run/audit tables and inside the LOC ceiling.
    records.migrate()
    # The mock core-banking store owns its own tables so its effects are as
    # inspectable as anything else in the trace (FR-9).
    core_banking.migrate()
