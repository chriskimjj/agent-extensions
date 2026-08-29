"""SQLite connection and additive migration boundary."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path


SCHEMA_VERSION = 1
_DB_LOCK = threading.RLock()


def default_db_path() -> Path:
    return (
        Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
        / "discord-related-threads"
        / "relations.sqlite3"
    )


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS attention_schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_threads (
        thread_id TEXT PRIMARY KEY,
        scope_id TEXT,
        parent_channel_id TEXT,
        thread_name TEXT,
        first_seen_at TEXT NOT NULL,
        last_discord_activity_at TEXT,
        last_hermes_activity_at TEXT,
        last_hermes_message_id TEXT,
        last_user_interaction_at TEXT,
        acknowledged_at TEXT,
        acknowledged_message_id TEXT,
        closed_at TEXT,
        state_updated_at TEXT,
        registration_source TEXT NOT NULL,
        historical INTEGER NOT NULL DEFAULT 0 CHECK (historical IN (0, 1)),
        link_state TEXT NOT NULL DEFAULT 'unknown'
            CHECK (link_state IN ('unknown', 'accessible', 'inaccessible')),
        link_checked_at TEXT,
        archived INTEGER CHECK (archived IN (0, 1)),
        auto_archive_minutes INTEGER,
        archive_at TEXT,
        inaccessible_since_date TEXT,
        next_access_check_date TEXT,
        last_exposed_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attention_threads_scope
        ON attention_threads (scope_id, thread_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attention_threads_candidates
        ON attention_threads (closed_at, link_state, last_hermes_activity_at, last_exposed_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_reminders (
        thread_id TEXT PRIMARY KEY,
        due_local_date TEXT NOT NULL,
        days INTEGER NOT NULL,
        source_message_id TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        set_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        cancelled_at TEXT,
        FOREIGN KEY (thread_id) REFERENCES attention_threads(thread_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attention_reminders_due
        ON attention_reminders (active, due_local_date)
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_history_exclusions (
        message_id TEXT PRIMARY KEY,
        thread_id TEXT,
        scope_id TEXT,
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_command_receipts (
        source_message_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        scope_id TEXT,
        command TEXT NOT NULL,
        outcome_code TEXT NOT NULL,
        days INTEGER,
        due_local_date TEXT,
        safe_bad_arg TEXT,
        valid INTEGER NOT NULL CHECK (valid IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        logical_key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        target_channel_id TEXT NOT NULL,
        source_thread_id TEXT,
        source_message_id TEXT,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'attempting', 'delivered', 'superseded', 'abandoned')),
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT NOT NULL,
        last_error_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        delivered_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attention_outbox_due
        ON attention_outbox (status, next_attempt_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_activations (
        activation_id TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('initializing', 'ready')),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        snapshot_total INTEGER NOT NULL DEFAULT 0,
        accessible_total INTEGER,
        inaccessible_total INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_backfill_snapshot (
        activation_id TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'accessible', 'inaccessible')),
        updated_at TEXT NOT NULL,
        PRIMARY KEY (activation_id, thread_id),
        FOREIGN KEY (activation_id) REFERENCES attention_activations(activation_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attention_backfill_pending
        ON attention_backfill_snapshot (activation_id, status, thread_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS attention_runtime_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


def migrate(path: Path | None = None) -> None:
    """Apply the feature schema atomically and verify database integrity."""

    with _DB_LOCK, closing(connect(path)) as conn, conn:
        before = conn.execute("PRAGMA quick_check").fetchone()
        if before is None or before[0] != "ok":
            raise sqlite3.DatabaseError("SQLite quick_check failed before migration")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.execute(
                """
                INSERT INTO attention_schema_meta (key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        after = conn.execute("PRAGMA quick_check").fetchone()
        if after is None or after[0] != "ok":
            raise sqlite3.DatabaseError("SQLite quick_check failed after migration")


def quick_check(path: Path | None = None) -> str:
    with _DB_LOCK, closing(connect(path)) as conn, conn:
        row = conn.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "missing"
