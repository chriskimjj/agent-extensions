"""Transactional repository for inventory, commands, backfill and delivery."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .commands import CommandAction, CommandAttempt
from .database import connect, default_db_path, migrate


UTC = timezone.utc
_DIGEST_CHANNEL_OUTAGE_KEY = "digest_channel_outage"
_APPLIED_COMMAND_OUTCOMES = frozenset(
    {
        "seen",
        "reminder_set",
        "reminder_cancelled",
        "reminder_already_clear",
        "closed",
    }
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: datetime | None = None) -> str:
    return as_utc(value).isoformat()


@dataclass(frozen=True)
class CommandCommitResult:
    outcome_code: str
    command: str
    valid: bool
    days: int | None
    due_local_date: str | None
    safe_bad_arg: str | None
    duplicate: bool = False


@dataclass(frozen=True)
class OutboxItem:
    id: int
    logical_key: str
    kind: str
    target_channel_id: str
    source_thread_id: str | None
    source_message_id: str | None
    payload: Mapping[str, Any]
    attempts: int


class AttentionRepository:
    """Profile-local durable state.

    A connection is opened per operation.  This keeps the object safe for the
    synchronous gateway hook and the asynchronous delivery worker without
    sharing SQLite connection state across threads.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self._lock = threading.RLock()

    def migrate(self) -> None:
        migrate(self.path)

    def _connect(self) -> sqlite3.Connection:
        return connect(self.path)

    @staticmethod
    def _max_timestamp(existing: str | None, candidate: str) -> str:
        return candidate if not existing or candidate > existing else existing

    @staticmethod
    def _acknowledgement_boundary(
        row: Mapping[str, Any], timestamp: str
    ) -> tuple[str, str | None]:
        """Acknowledge only Hermes activity that existed by the event time."""

        activity_at = row["last_hermes_activity_at"]
        if activity_at and str(activity_at) <= timestamp:
            return str(activity_at), row["last_hermes_message_id"]
        return timestamp, None

    @staticmethod
    def _ensure_thread(
        conn: sqlite3.Connection,
        *,
        thread_id: str,
        observed_at: str,
        scope_id: str | None = None,
        parent_channel_id: str | None = None,
        thread_name: str | None = None,
        registration_source: str = "live",
        historical: bool = False,
    ) -> None:
        conn.execute(
            """
            INSERT INTO attention_threads (
                thread_id, scope_id, parent_channel_id, thread_name,
                first_seen_at, registration_source, historical, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                scope_id=COALESCE(excluded.scope_id, attention_threads.scope_id),
                parent_channel_id=COALESCE(
                    excluded.parent_channel_id,
                    attention_threads.parent_channel_id
                ),
                thread_name=COALESCE(excluded.thread_name, attention_threads.thread_name),
                first_seen_at=CASE
                    WHEN excluded.first_seen_at < attention_threads.first_seen_at
                    THEN excluded.first_seen_at ELSE attention_threads.first_seen_at END,
                registration_source=CASE
                    WHEN attention_threads.historical=1 OR excluded.historical=1
                    THEN 'backfill' ELSE attention_threads.registration_source END,
                historical=CASE
                    WHEN attention_threads.historical=1 OR excluded.historical=1 THEN 1 ELSE 0 END,
                updated_at=CASE
                    WHEN excluded.updated_at > attention_threads.updated_at
                    THEN excluded.updated_at ELSE attention_threads.updated_at END
            """,
            (
                thread_id,
                scope_id,
                parent_channel_id,
                thread_name,
                observed_at,
                registration_source,
                1 if historical else 0,
                observed_at,
            ),
        )

    @staticmethod
    def _is_snapshot_thread(conn: sqlite3.Connection, thread_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM attention_backfill_snapshot WHERE thread_id=? LIMIT 1",
            (thread_id,),
        ).fetchone()
        return row is not None

    def record_thread_participation(
        self,
        thread_id: str,
        *,
        observed_at: datetime | None = None,
        scope_id: str | None = None,
        parent_channel_id: str | None = None,
        thread_name: str | None = None,
    ) -> None:
        if not thread_id:
            return
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                historical = self._is_snapshot_thread(conn, thread_id)
                self._ensure_thread(
                    conn,
                    thread_id=thread_id,
                    observed_at=timestamp,
                    scope_id=scope_id,
                    parent_channel_id=parent_channel_id,
                    thread_name=thread_name,
                    registration_source="backfill" if historical else "live",
                    historical=historical,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_user_interaction(
        self,
        *,
        thread_id: str,
        message_id: str | None,
        observed_at: datetime | None,
        scope_id: str | None,
        parent_channel_id: str | None,
        thread_name: str | None,
    ) -> None:
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                historical = self._is_snapshot_thread(conn, thread_id)
                self._ensure_thread(
                    conn,
                    thread_id=thread_id,
                    observed_at=timestamp,
                    scope_id=scope_id,
                    parent_channel_id=parent_channel_id,
                    thread_name=thread_name,
                    registration_source="backfill" if historical else "live",
                    historical=historical,
                )
                row = conn.execute(
                    """
                    SELECT last_hermes_activity_at, last_hermes_message_id,
                           last_user_interaction_at, acknowledged_at,
                           acknowledged_message_id, closed_at,
                           state_updated_at, last_discord_activity_at
                      FROM attention_threads WHERE thread_id=?
                    """,
                    (thread_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.IntegrityError("inventory row missing after upsert")
                interaction_at = self._max_timestamp(
                    row["last_user_interaction_at"], timestamp
                )
                discord_at = self._max_timestamp(
                    row["last_discord_activity_at"], timestamp
                )
                if row["acknowledged_at"] and row["acknowledged_at"] > timestamp:
                    acknowledged_at = row["acknowledged_at"]
                    acknowledged_message_id = row["acknowledged_message_id"]
                else:
                    acknowledged_at, acknowledged_message_id = (
                        self._acknowledgement_boundary(row, timestamp)
                    )
                closed_at = row["closed_at"]
                if closed_at is not None and timestamp >= closed_at:
                    closed_at = None
                state_updated_at = self._max_timestamp(row["state_updated_at"], timestamp)
                conn.execute(
                    """
                    UPDATE attention_threads
                       SET last_discord_activity_at=?,
                           last_user_interaction_at=?,
                           acknowledged_at=?,
                           acknowledged_message_id=?,
                           closed_at=?,
                           state_updated_at=?,
                           updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                     WHERE thread_id=?
                    """,
                    (
                        discord_at,
                        interaction_at,
                        acknowledged_at,
                        acknowledged_message_id,
                        closed_at,
                        state_updated_at,
                        timestamp,
                        timestamp,
                        thread_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_hermes_activity(
        self,
        *,
        thread_id: str,
        message_id: str | None,
        observed_at: datetime | None,
        scope_id: str | None,
        parent_channel_id: str | None,
        thread_name: str | None,
    ) -> None:
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                historical = self._is_snapshot_thread(conn, thread_id)
                self._ensure_thread(
                    conn,
                    thread_id=thread_id,
                    observed_at=timestamp,
                    scope_id=scope_id,
                    parent_channel_id=parent_channel_id,
                    thread_name=thread_name,
                    registration_source="backfill" if historical else "live",
                    historical=historical,
                )
                row = conn.execute(
                    """
                    SELECT last_hermes_activity_at, last_discord_activity_at
                      FROM attention_threads WHERE thread_id=?
                    """,
                    (thread_id,),
                ).fetchone()
                newer = row is None or not row["last_hermes_activity_at"] or (
                    timestamp >= row["last_hermes_activity_at"]
                )
                conn.execute(
                    """
                    UPDATE attention_threads
                       SET last_hermes_activity_at=CASE WHEN ? THEN ? ELSE last_hermes_activity_at END,
                           last_hermes_message_id=CASE WHEN ? THEN ? ELSE last_hermes_message_id END,
                           last_discord_activity_at=CASE
                               WHEN last_discord_activity_at IS NULL OR ? > last_discord_activity_at
                               THEN ? ELSE last_discord_activity_at END,
                           updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                     WHERE thread_id=?
                    """,
                    (
                        1 if newer else 0,
                        timestamp,
                        1 if newer else 0,
                        message_id,
                        timestamp,
                        timestamp,
                        timestamp,
                        timestamp,
                        thread_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _receipt_result(row: sqlite3.Row, *, duplicate: bool) -> CommandCommitResult:
        return CommandCommitResult(
            outcome_code=str(row["outcome_code"]),
            command=str(row["command"]),
            valid=bool(row["valid"]),
            days=row["days"],
            due_local_date=row["due_local_date"],
            safe_bad_arg=row["safe_bad_arg"],
            duplicate=duplicate,
        )

    def process_command(
        self,
        *,
        attempt: CommandAttempt,
        source_message_id: str,
        thread_id: str,
        scope_id: str | None,
        target_channel_id: str,
        observed_at: datetime | None,
        due_local_date: date | None = None,
        forced_outcome: str | None = None,
    ) -> CommandCommitResult:
        """Commit a command attempt, exclusion and confirmation obligation once."""

        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT * FROM attention_command_receipts WHERE source_message_id=?",
                    (source_message_id,),
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    return self._receipt_result(existing, duplicate=True)

                outcome = forced_outcome
                due_text = due_local_date.isoformat() if due_local_date else None
                if outcome is None and not attempt.valid:
                    outcome = attempt.error_code or "invalid"

                # Reminder cancellation is intentionally ledger-only: unlike
                # seen/remind/close it must not create or mutate inventory.
                if outcome is None and attempt.action is CommandAction.CANCEL_REMINDER:
                    reminder = conn.execute(
                        "SELECT active, updated_at FROM attention_reminders WHERE thread_id=?",
                        (thread_id,),
                    ).fetchone()
                    was_active = bool(reminder and reminder["active"])
                    if reminder is not None and timestamp >= reminder["updated_at"]:
                        conn.execute(
                            """
                            UPDATE attention_reminders
                               SET active=0, cancelled_at=?, updated_at=?
                             WHERE thread_id=?
                            """,
                            (timestamp, timestamp, thread_id),
                        )
                    outcome = (
                        "reminder_cancelled" if was_active else "reminder_already_clear"
                    )

                if outcome is None:
                    historical = self._is_snapshot_thread(conn, thread_id)
                    self._ensure_thread(
                        conn,
                        thread_id=thread_id,
                        observed_at=timestamp,
                        scope_id=scope_id,
                        registration_source="backfill" if historical else "live",
                        historical=historical,
                    )
                    row = conn.execute(
                        "SELECT * FROM attention_threads WHERE thread_id=?",
                        (thread_id,),
                    ).fetchone()
                    if row is None:
                        raise sqlite3.IntegrityError("inventory row missing after upsert")

                    if attempt.action is CommandAction.SEEN:
                        ack_at, ack_message_id = self._acknowledgement_boundary(
                            row, timestamp
                        )
                        conn.execute(
                            """
                            UPDATE attention_threads
                               SET last_user_interaction_at=CASE
                                       WHEN last_user_interaction_at IS NULL OR ? > last_user_interaction_at
                                       THEN ? ELSE last_user_interaction_at END,
                                   acknowledged_at=CASE
                                       WHEN acknowledged_at IS NULL OR ? >= COALESCE(state_updated_at, '')
                                       THEN ? ELSE acknowledged_at END,
                                   acknowledged_message_id=CASE
                                       WHEN ? >= COALESCE(state_updated_at, '')
                                       THEN ? ELSE acknowledged_message_id END,
                                   closed_at=CASE
                                       WHEN closed_at IS NULL OR ? >= closed_at THEN NULL ELSE closed_at END,
                                   state_updated_at=CASE
                                       WHEN state_updated_at IS NULL OR ? > state_updated_at
                                       THEN ? ELSE state_updated_at END,
                                   updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                             WHERE thread_id=?
                            """,
                            (
                                timestamp,
                                timestamp,
                                timestamp,
                                ack_at,
                                timestamp,
                                ack_message_id,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                thread_id,
                            ),
                        )
                        outcome = "seen"
                    elif attempt.action is CommandAction.REMIND:
                        if due_text is None or attempt.days is None:
                            raise ValueError("valid reminder requires a due date and days")
                        ack_at, ack_message_id = self._acknowledgement_boundary(
                            row, timestamp
                        )
                        conn.execute(
                            """
                            UPDATE attention_threads
                               SET last_user_interaction_at=CASE
                                       WHEN last_user_interaction_at IS NULL OR ? > last_user_interaction_at
                                       THEN ? ELSE last_user_interaction_at END,
                                   acknowledged_at=CASE
                                       WHEN acknowledged_at IS NULL OR ? >= COALESCE(state_updated_at, '')
                                       THEN ? ELSE acknowledged_at END,
                                   acknowledged_message_id=CASE
                                       WHEN ? >= COALESCE(state_updated_at, '')
                                       THEN ? ELSE acknowledged_message_id END,
                                   closed_at=CASE
                                       WHEN closed_at IS NULL OR ? >= closed_at THEN NULL ELSE closed_at END,
                                   state_updated_at=CASE
                                       WHEN state_updated_at IS NULL OR ? > state_updated_at
                                       THEN ? ELSE state_updated_at END,
                                   updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                             WHERE thread_id=?
                            """,
                            (
                                timestamp,
                                timestamp,
                                timestamp,
                                ack_at,
                                timestamp,
                                ack_message_id,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                thread_id,
                            ),
                        )
                        current_reminder = conn.execute(
                            "SELECT updated_at FROM attention_reminders WHERE thread_id=?",
                            (thread_id,),
                        ).fetchone()
                        if current_reminder is None or timestamp >= current_reminder["updated_at"]:
                            conn.execute(
                                """
                                INSERT INTO attention_reminders (
                                    thread_id, due_local_date, days, source_message_id,
                                    active, set_at, updated_at, cancelled_at
                                ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
                                ON CONFLICT(thread_id) DO UPDATE SET
                                    due_local_date=excluded.due_local_date,
                                    days=excluded.days,
                                    source_message_id=excluded.source_message_id,
                                    active=1,
                                    set_at=excluded.set_at,
                                    updated_at=excluded.updated_at,
                                    cancelled_at=NULL
                                """,
                                (
                                    thread_id,
                                    due_text,
                                    attempt.days,
                                    source_message_id,
                                    timestamp,
                                    timestamp,
                                ),
                            )
                        outcome = "reminder_set"
                    elif attempt.action is CommandAction.CLOSE:
                        conn.execute(
                            """
                            UPDATE attention_threads
                               SET closed_at=CASE
                                       WHEN state_updated_at IS NULL OR ? >= state_updated_at
                                       THEN ? ELSE closed_at END,
                                   state_updated_at=CASE
                                       WHEN state_updated_at IS NULL OR ? > state_updated_at
                                       THEN ? ELSE state_updated_at END,
                                   updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                             WHERE thread_id=?
                            """,
                            (
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                timestamp,
                                thread_id,
                            ),
                        )
                        reminder = conn.execute(
                            "SELECT updated_at FROM attention_reminders WHERE thread_id=?",
                            (thread_id,),
                        ).fetchone()
                        if reminder is not None and timestamp >= reminder["updated_at"]:
                            conn.execute(
                                """
                                UPDATE attention_reminders
                                   SET active=0, cancelled_at=?, updated_at=?
                                 WHERE thread_id=?
                                """,
                                (timestamp, timestamp, thread_id),
                            )
                        outcome = "closed"
                    else:
                        raise ValueError("unsupported command action")

                assert outcome is not None
                safe_bad_arg = attempt.safe_bad_arg if not attempt.valid else None
                conn.execute(
                    """
                    INSERT INTO attention_command_receipts (
                        source_message_id, thread_id, scope_id, command,
                        outcome_code, days, due_local_date, safe_bad_arg, valid, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_message_id,
                        thread_id,
                        scope_id,
                        attempt.command,
                        outcome,
                        attempt.days,
                        due_text,
                        safe_bad_arg,
                        1 if attempt.valid else 0,
                        timestamp,
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO attention_history_exclusions (
                        message_id, thread_id, scope_id, kind, created_at
                    ) VALUES (?, ?, ?, 'command', ?)
                    """,
                    (source_message_id, thread_id, scope_id, timestamp),
                )
                payload = json.dumps(
                    {
                        "outcome_code": outcome,
                        "command": attempt.command,
                        "days": attempt.days,
                        "due_local_date": due_text,
                        "safe_bad_arg": safe_bad_arg,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO attention_outbox (
                        logical_key, kind, target_channel_id, source_thread_id,
                        source_message_id, payload_json, status, attempts,
                        next_attempt_at, created_at, updated_at
                    ) VALUES (?, 'command_confirmation', ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                    """,
                    (
                        f"command:{source_message_id}",
                        target_channel_id,
                        thread_id,
                        source_message_id,
                        payload,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                conn.commit()
                return CommandCommitResult(
                    outcome_code=outcome,
                    command=attempt.command,
                    valid=attempt.valid,
                    days=attempt.days,
                    due_local_date=due_text,
                    safe_bad_arg=safe_bad_arg,
                )
            except Exception:
                conn.rollback()
                raise

    def has_history_exclusion(self, message_id: str) -> bool:
        if not message_id:
            return False
        with self._lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT 1 FROM attention_history_exclusions WHERE message_id=?",
                (message_id,),
            ).fetchone()
        return row is not None

    def ensure_activation(
        self,
        thread_ids: Iterable[str],
        *,
        observed_at: datetime | None = None,
    ) -> str:
        timestamp = iso(observed_at)
        ids = sorted({str(thread_id) for thread_id in thread_ids if str(thread_id)})
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT activation_id FROM attention_activations ORDER BY started_at LIMIT 1"
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    return str(existing["activation_id"])
                activation_id = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO attention_activations (
                        activation_id, status, started_at, snapshot_total
                    ) VALUES (?, 'initializing', ?, ?)
                    """,
                    (activation_id, timestamp, len(ids)),
                )
                conn.executemany(
                    """
                    INSERT INTO attention_backfill_snapshot (
                        activation_id, thread_id, status, updated_at
                    ) VALUES (?, ?, 'pending', ?)
                    """,
                    ((activation_id, thread_id, timestamp) for thread_id in ids),
                )
                conn.commit()
                return activation_id
            except Exception:
                conn.rollback()
                raise

    def reconcile_participation_ids(
        self,
        thread_ids: Iterable[str],
        *,
        observed_at: datetime | None = None,
    ) -> int:
        """Ensure every currently durable participation ID is inventoried.

        The first activation snapshot stays immutable.  IDs accumulated while
        the feature was later disabled are therefore registered as live on the
        next enable instead of silently falling outside both the old snapshot
        and the live participation hook.
        """

        timestamp = iso(observed_at)
        ids = sorted({str(thread_id) for thread_id in thread_ids if str(thread_id)})
        if not ids:
            return 0
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                snapshot_ids = {
                    str(row["thread_id"])
                    for row in conn.execute(
                        "SELECT DISTINCT thread_id FROM attention_backfill_snapshot"
                    ).fetchall()
                }
                before = conn.total_changes
                for thread_id in ids:
                    historical = thread_id in snapshot_ids
                    self._ensure_thread(
                        conn,
                        thread_id=thread_id,
                        observed_at=timestamp,
                        registration_source="backfill" if historical else "live",
                        historical=historical,
                    )
                changed = conn.total_changes - before
                conn.commit()
                return changed
            except Exception:
                conn.rollback()
                raise

    def activation_status(self, activation_id: str) -> str | None:
        with self._lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT status FROM attention_activations WHERE activation_id=?",
                (activation_id,),
            ).fetchone()
        return str(row["status"]) if row else None

    def pending_backfill(self, activation_id: str, *, limit: int = 25) -> list[str]:
        with self._lock, closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT thread_id FROM attention_backfill_snapshot
                 WHERE activation_id=? AND status='pending'
                 ORDER BY thread_id LIMIT ?
                """,
                (activation_id, max(1, limit)),
            ).fetchall()
        return [str(row["thread_id"]) for row in rows]

    def record_backfill_result(
        self,
        *,
        activation_id: str,
        thread_id: str,
        metadata: Mapping[str, Any] | None,
        local_date: date,
        observed_at: datetime | None = None,
    ) -> None:
        timestamp = iso(observed_at)
        accessible = bool(metadata and metadata.get("accessible"))
        status = "accessible" if accessible else "inaccessible"
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_thread(
                    conn,
                    thread_id=thread_id,
                    observed_at=timestamp,
                    scope_id=str(metadata.get("scope_id")) if metadata and metadata.get("scope_id") else None,
                    parent_channel_id=(
                        str(metadata.get("parent_channel_id"))
                        if metadata and metadata.get("parent_channel_id")
                        else None
                    ),
                    thread_name=(
                        str(metadata.get("thread_name"))
                        if metadata and metadata.get("thread_name")
                        else None
                    ),
                    registration_source="backfill",
                    historical=True,
                )
                if accessible:
                    last_discord_activity = (
                        metadata.get("last_discord_activity_at")
                        or metadata.get("last_activity_at")
                        if metadata
                        else None
                    )
                    last_hermes_activity = (
                        metadata.get("last_hermes_activity_at")
                        or metadata.get("last_activity_at")
                        if metadata
                        else None
                    )
                    archive_at = metadata.get("archive_at") if metadata else None
                    conn.execute(
                        """
                        UPDATE attention_threads
                           SET link_state='accessible', link_checked_at=?,
                               archived=?, auto_archive_minutes=?, archive_at=?,
                               last_discord_activity_at=CASE
                                   WHEN ? IS NOT NULL AND
                                        (last_discord_activity_at IS NULL OR ? > last_discord_activity_at)
                                   THEN ? ELSE last_discord_activity_at END,
                               last_hermes_activity_at=CASE
                                   WHEN ? IS NOT NULL AND
                                        (last_hermes_activity_at IS NULL OR ? > last_hermes_activity_at)
                                   THEN ? ELSE last_hermes_activity_at END,
                               inaccessible_since_date=NULL, next_access_check_date=NULL,
                               updated_at=?
                         WHERE thread_id=?
                        """,
                        (
                            timestamp,
                            1 if metadata.get("archived") else 0,
                            metadata.get("auto_archive_minutes"),
                            iso(archive_at) if isinstance(archive_at, datetime) else archive_at,
                            iso(last_discord_activity)
                            if isinstance(last_discord_activity, datetime)
                            else last_discord_activity,
                            iso(last_discord_activity)
                            if isinstance(last_discord_activity, datetime)
                            else last_discord_activity,
                            iso(last_discord_activity)
                            if isinstance(last_discord_activity, datetime)
                            else last_discord_activity,
                            iso(last_hermes_activity)
                            if isinstance(last_hermes_activity, datetime)
                            else last_hermes_activity,
                            iso(last_hermes_activity)
                            if isinstance(last_hermes_activity, datetime)
                            else last_hermes_activity,
                            iso(last_hermes_activity)
                            if isinstance(last_hermes_activity, datetime)
                            else last_hermes_activity,
                            timestamp,
                            thread_id,
                        ),
                    )
                else:
                    next_date = (local_date + timedelta(days=1)).isoformat()
                    conn.execute(
                        """
                        UPDATE attention_threads
                           SET link_state='inaccessible', link_checked_at=?,
                               inaccessible_since_date=COALESCE(inaccessible_since_date, ?),
                               next_access_check_date=?, updated_at=?
                         WHERE thread_id=?
                        """,
                        (timestamp, local_date.isoformat(), next_date, timestamp, thread_id),
                    )
                conn.execute(
                    """
                    UPDATE attention_backfill_snapshot
                       SET status=?, updated_at=?
                     WHERE activation_id=? AND thread_id=?
                    """,
                    (status, timestamp, activation_id, thread_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def metadata_refresh_thread_ids(
        self,
        *,
        local_date: date,
        accessible_checked_before: datetime | None = None,
        limit: int = 20,
    ) -> list[str]:
        """Return unknown, scheduled-inaccessible, or stale accessible IDs."""

        with self._lock, closing(self._connect()) as conn, conn:
            params: list[Any] = [local_date.isoformat()]
            accessible_clause = ""
            if accessible_checked_before is not None:
                accessible_clause = (
                    " OR (link_state='accessible' AND "
                    "(link_checked_at IS NULL OR link_checked_at<?))"
                )
                params.append(iso(accessible_checked_before))
            params.append(max(1, limit))
            rows = conn.execute(
                f"""
                SELECT thread_id FROM attention_threads
                 WHERE link_state='unknown'
                    OR (link_state='inaccessible'
                        AND (next_access_check_date IS NULL OR next_access_check_date<=?))
                    {accessible_clause}
                 ORDER BY CASE link_state
                              WHEN 'unknown' THEN 0
                              WHEN 'inaccessible' THEN 1
                              ELSE 2
                          END,
                          COALESCE(next_access_check_date, ''), thread_id
                 LIMIT ?
                """,
                params,
            ).fetchall()
        return [str(row["thread_id"]) for row in rows]

    def record_metadata_result(
        self,
        *,
        thread_id: str,
        metadata: Mapping[str, Any] | None,
        local_date: date,
        observed_at: datetime | None = None,
    ) -> None:
        """Refresh link/activity/archive metadata without storing message text."""

        timestamp = iso(observed_at)
        accessible = bool(metadata and metadata.get("accessible"))
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT * FROM attention_threads WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()
                if existing is None:
                    self._ensure_thread(
                        conn,
                        thread_id=thread_id,
                        observed_at=timestamp,
                        registration_source="live",
                    )
                    existing = conn.execute(
                        "SELECT * FROM attention_threads WHERE thread_id=?",
                        (thread_id,),
                    ).fetchone()
                if accessible:
                    last_discord = metadata.get("last_discord_activity_at")
                    last_hermes = metadata.get("last_hermes_activity_at")
                    archive_at = metadata.get("archive_at")
                    last_discord_text = (
                        iso(last_discord)
                        if isinstance(last_discord, datetime)
                        else last_discord
                    )
                    last_hermes_text = (
                        iso(last_hermes)
                        if isinstance(last_hermes, datetime)
                        else last_hermes
                    )
                    archive_text = (
                        iso(archive_at) if isinstance(archive_at, datetime) else archive_at
                    )
                    conn.execute(
                        """
                        UPDATE attention_threads
                           SET scope_id=COALESCE(?, scope_id),
                               parent_channel_id=COALESCE(?, parent_channel_id),
                               thread_name=COALESCE(?, thread_name),
                               link_state='accessible', link_checked_at=?,
                               archived=?, auto_archive_minutes=?, archive_at=?,
                               last_discord_activity_at=CASE
                                   WHEN ? IS NOT NULL AND
                                        (last_discord_activity_at IS NULL OR ? > last_discord_activity_at)
                                   THEN ? ELSE last_discord_activity_at END,
                               last_hermes_activity_at=CASE
                                   WHEN ? IS NOT NULL AND
                                        (last_hermes_activity_at IS NULL OR ? > last_hermes_activity_at)
                                   THEN ? ELSE last_hermes_activity_at END,
                               inaccessible_since_date=NULL,
                               next_access_check_date=NULL,
                               updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                         WHERE thread_id=?
                        """,
                        (
                            str(metadata.get("scope_id")) if metadata.get("scope_id") else None,
                            str(metadata.get("parent_channel_id"))
                            if metadata.get("parent_channel_id")
                            else None,
                            str(metadata.get("thread_name"))
                            if metadata.get("thread_name")
                            else None,
                            timestamp,
                            1 if metadata.get("archived") else 0,
                            metadata.get("auto_archive_minutes"),
                            archive_text,
                            last_discord_text,
                            last_discord_text,
                            last_discord_text,
                            last_hermes_text,
                            last_hermes_text,
                            last_hermes_text,
                            timestamp,
                            timestamp,
                            thread_id,
                        ),
                    )
                else:
                    since_text = existing["inaccessible_since_date"] or local_date.isoformat()
                    try:
                        since_date = date.fromisoformat(str(since_text))
                    except ValueError:
                        since_date = local_date
                        since_text = local_date.isoformat()
                    elapsed_days = max(0, (local_date - since_date).days)
                    delay_days = 1 if elapsed_days < 6 else 7
                    next_date = (local_date + timedelta(days=delay_days)).isoformat()
                    conn.execute(
                        """
                        UPDATE attention_threads
                           SET link_state='inaccessible', link_checked_at=?,
                               inaccessible_since_date=?, next_access_check_date=?,
                               updated_at=CASE WHEN ? > updated_at THEN ? ELSE updated_at END
                         WHERE thread_id=?
                        """,
                        (
                            timestamp,
                            since_text,
                            next_date,
                            timestamp,
                            timestamp,
                            thread_id,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def complete_activation_if_ready(
        self,
        *,
        activation_id: str,
        digest_channel_id: str,
        observed_at: datetime | None = None,
    ) -> bool:
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                activation = conn.execute(
                    "SELECT * FROM attention_activations WHERE activation_id=?",
                    (activation_id,),
                ).fetchone()
                if activation is None:
                    raise KeyError(f"unknown activation {activation_id}")
                if activation["status"] == "ready":
                    conn.commit()
                    return False
                counts = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                        SUM(CASE WHEN status='accessible' THEN 1 ELSE 0 END) AS accessible,
                        SUM(CASE WHEN status='inaccessible' THEN 1 ELSE 0 END) AS inaccessible
                      FROM attention_backfill_snapshot WHERE activation_id=?
                    """,
                    (activation_id,),
                ).fetchone()
                if counts and int(counts["pending"] or 0) > 0:
                    conn.commit()
                    return False
                total = int(counts["total"] or 0) if counts else 0
                accessible = int(counts["accessible"] or 0) if counts else 0
                inaccessible = int(counts["inaccessible"] or 0) if counts else 0
                conn.execute(
                    """
                    UPDATE attention_activations
                       SET status='ready', completed_at=?, snapshot_total=?,
                           accessible_total=?, inaccessible_total=?
                     WHERE activation_id=?
                    """,
                    (timestamp, total, accessible, inaccessible, activation_id),
                )
                payload = json.dumps(
                    {
                        "total": total,
                        "accessible": accessible,
                        "inaccessible": inaccessible,
                    },
                    separators=(",", ":"),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO attention_outbox (
                        logical_key, kind, target_channel_id, payload_json,
                        status, attempts, next_attempt_at, created_at, updated_at
                    ) VALUES (?, 'initial_summary', ?, ?, 'pending', 0, ?, ?, ?)
                    """,
                    (
                        f"initial:{activation_id}",
                        digest_channel_id,
                        payload,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def ensure_digest_outbox(
        self,
        *,
        local_date: date,
        digest_channel_id: str,
        observed_at: datetime | None = None,
    ) -> bool:
        timestamp = iso(observed_at)
        date_text = local_date.isoformat()
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    UPDATE attention_outbox
                       SET status='superseded', updated_at=?
                     WHERE kind='digest' AND status IN ('pending', 'attempting')
                       AND json_extract(payload_json, '$.local_date') < ?
                    """,
                    (timestamp, date_text),
                )
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO attention_outbox (
                        logical_key, kind, target_channel_id, payload_json,
                        status, attempts, next_attempt_at, created_at, updated_at
                    ) VALUES (?, 'digest', ?, ?, 'pending', 0, ?, ?, ?)
                    """,
                    (
                        f"digest:{date_text}",
                        digest_channel_id,
                        json.dumps({"local_date": date_text}, separators=(",", ":")),
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                created = cursor.rowcount > 0
                conn.commit()
                return created
            except Exception:
                conn.rollback()
                raise

    def recover_attempting(self, *, observed_at: datetime | None = None) -> int:
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                UPDATE attention_outbox
                   SET status='pending', next_attempt_at=?, updated_at=?
                 WHERE status='attempting'
                """,
                (timestamp, timestamp),
            )
        return int(cursor.rowcount)

    def claim_due_outbox(
        self,
        *,
        observed_at: datetime | None = None,
        allowed_kinds: Sequence[str] | None = None,
    ) -> OutboxItem | None:
        timestamp = iso(observed_at)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                params: list[Any] = [timestamp]
                where = "status='pending' AND next_attempt_at<=?"
                if allowed_kinds is not None:
                    kinds = tuple(allowed_kinds)
                    if not kinds:
                        conn.commit()
                        return None
                    where += " AND kind IN ({})".format(",".join("?" for _ in kinds))
                    params.extend(kinds)
                row = conn.execute(
                    f"""
                    SELECT * FROM attention_outbox
                     WHERE {where}
                     ORDER BY next_attempt_at, id LIMIT 1
                    """,
                    params,
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                attempts = int(row["attempts"]) + 1
                updated = conn.execute(
                    """
                    UPDATE attention_outbox
                       SET status='attempting', attempts=?, updated_at=?
                     WHERE id=? AND status='pending'
                    """,
                    (attempts, timestamp, row["id"]),
                )
                if updated.rowcount != 1:
                    conn.rollback()
                    return None
                conn.commit()
                return OutboxItem(
                    id=int(row["id"]),
                    logical_key=str(row["logical_key"]),
                    kind=str(row["kind"]),
                    target_channel_id=str(row["target_channel_id"]),
                    source_thread_id=row["source_thread_id"],
                    source_message_id=row["source_message_id"],
                    payload=json.loads(row["payload_json"]),
                    attempts=attempts,
                )
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def retry_delay(attempts: int) -> timedelta:
        if attempts <= 1:
            return timedelta(minutes=1)
        if attempts == 2:
            return timedelta(minutes=5)
        if attempts == 3:
            return timedelta(minutes=30)
        return timedelta(hours=3)

    def mark_outbox_failed(
        self,
        outbox_id: int,
        *,
        attempts: int,
        error_code: str,
        observed_at: datetime | None = None,
        abandoned: bool = False,
        record_digest_outage: bool = False,
    ) -> bool:
        """Persist a failed attempt and optionally open one channel outage.

        Returns ``True`` only when this call created the outage record.  That
        lets the runtime write one local error log per outage instead of one
        log line per retry.
        """

        now = as_utc(observed_at)
        next_attempt = now + self.retry_delay(attempts)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                updated = conn.execute(
                    """
                    UPDATE attention_outbox
                       SET status=?, next_attempt_at=?, last_error_code=?, updated_at=?
                     WHERE id=? AND status='attempting'
                    """,
                    (
                        "abandoned" if abandoned else "pending",
                        iso(next_attempt),
                        error_code[:80],
                        iso(now),
                        outbox_id,
                    ),
                )
                outage_started = False
                if updated.rowcount == 1 and record_digest_outage:
                    outage_payload = json.dumps(
                        {
                            "started_at": iso(now),
                            "error_code": error_code[:80],
                        },
                        separators=(",", ":"),
                    )
                    created = conn.execute(
                        """
                        INSERT OR IGNORE INTO attention_runtime_state (
                            key, value, updated_at
                        ) VALUES (?, ?, ?)
                        """,
                        (_DIGEST_CHANNEL_OUTAGE_KEY, outage_payload, iso(now)),
                    )
                    outage_started = created.rowcount > 0
                conn.commit()
                return outage_started
            except Exception:
                conn.rollback()
                raise

    def abandon_source_confirmation_and_warn(
        self,
        outbox_id: int,
        *,
        error_code: str,
        digest_channel_id: str,
        observed_at: datetime | None = None,
    ) -> bool:
        """Atomically abandon a source confirmation and enqueue its warning."""

        now = as_utc(observed_at)
        timestamp = iso(now)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT o.kind, o.source_thread_id, o.source_message_id,
                           o.payload_json, r.scope_id
                      FROM attention_outbox o
                 LEFT JOIN attention_command_receipts r
                        ON r.source_message_id=o.source_message_id
                     WHERE o.id=? AND o.status='attempting'
                    """,
                    (outbox_id,),
                ).fetchone()
                if row is None or row["kind"] != "command_confirmation":
                    conn.commit()
                    return False
                updated = conn.execute(
                    """
                    UPDATE attention_outbox
                       SET status='abandoned', next_attempt_at=?,
                           last_error_code=?, updated_at=?
                     WHERE id=? AND status='attempting'
                    """,
                    (timestamp, error_code[:80], timestamp, outbox_id),
                )
                if updated.rowcount != 1:
                    conn.rollback()
                    return False
                source_payload = json.loads(row["payload_json"])
                outcome_code = str(source_payload.get("outcome_code") or "db_error")
                warning_payload = json.dumps(
                    {
                        "thread_id": str(row["source_thread_id"] or ""),
                        "scope_id": str(row["scope_id"] or ""),
                        "applied": outcome_code in _APPLIED_COMMAND_OUTCOMES,
                        "error_code": error_code[:80],
                    },
                    separators=(",", ":"),
                )
                created = conn.execute(
                    """
                    INSERT OR IGNORE INTO attention_outbox (
                        logical_key, kind, target_channel_id, source_thread_id,
                        payload_json, status, attempts, next_attempt_at,
                        created_at, updated_at
                    ) VALUES (?, 'source_warning', ?, ?, ?, 'pending', 0, ?, ?, ?)
                    """,
                    (
                        f"source-warning:{outbox_id}",
                        digest_channel_id,
                        row["source_thread_id"],
                        warning_payload,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                conn.commit()
                return created.rowcount > 0
            except Exception:
                conn.rollback()
                raise

    def mark_outbox_delivered(
        self,
        outbox_id: int,
        *,
        message_ids: Iterable[str] = (),
        exposed_thread_ids: Iterable[str] = (),
        observed_at: datetime | None = None,
        digest_channel_id: str | None = None,
    ) -> bool:
        """Mark delivery and atomically enqueue one outage-recovery warning.

        Returns whether a recovery warning was created.
        """

        timestamp = iso(observed_at)
        ids = {str(message_id) for message_id in message_ids if str(message_id)}
        threads = {str(thread_id) for thread_id in exposed_thread_ids if str(thread_id)}
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT kind, source_thread_id, target_channel_id
                      FROM attention_outbox WHERE id=?
                    """,
                    (outbox_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown outbox row {outbox_id}")
                conn.execute(
                    """
                    UPDATE attention_outbox
                       SET status='delivered', delivered_at=?, updated_at=?, last_error_code=NULL
                     WHERE id=?
                    """,
                    (timestamp, timestamp, outbox_id),
                )
                if row["kind"] == "command_confirmation":
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO attention_history_exclusions (
                            message_id, thread_id, kind, created_at
                        ) VALUES (?, ?, 'confirmation', ?)
                        """,
                        (
                            (message_id, row["source_thread_id"], timestamp)
                            for message_id in ids
                        ),
                    )
                if threads:
                    conn.executemany(
                        """
                        UPDATE attention_threads
                           SET last_exposed_at=?, updated_at=CASE
                               WHEN ? > updated_at THEN ? ELSE updated_at END
                         WHERE thread_id=?
                        """,
                        (
                            (timestamp, timestamp, timestamp, thread_id)
                            for thread_id in threads
                        ),
                    )
                recovery_created = False
                if (
                    digest_channel_id
                    and str(row["target_channel_id"]) == str(digest_channel_id)
                ):
                    outage = conn.execute(
                        "SELECT value FROM attention_runtime_state WHERE key=?",
                        (_DIGEST_CHANNEL_OUTAGE_KEY,),
                    ).fetchone()
                    if outage is not None:
                        try:
                            outage_payload = json.loads(outage["value"])
                        except (TypeError, ValueError):
                            outage_payload = {}
                        started_at = str(
                            outage_payload.get("started_at") or timestamp
                        )
                        payload = json.dumps(
                            {
                                "started_at": started_at,
                                "recovered_at": timestamp,
                            },
                            separators=(",", ":"),
                        )
                        created = conn.execute(
                            """
                            INSERT OR IGNORE INTO attention_outbox (
                                logical_key, kind, target_channel_id,
                                payload_json, status, attempts, next_attempt_at,
                                created_at, updated_at
                            ) VALUES (?, 'channel_recovery', ?, ?, 'pending', 0, ?, ?, ?)
                            """,
                            (
                                f"channel-recovery:{started_at}",
                                digest_channel_id,
                                payload,
                                timestamp,
                                timestamp,
                                timestamp,
                            ),
                        )
                        recovery_created = created.rowcount > 0
                        conn.execute(
                            "DELETE FROM attention_runtime_state WHERE key=?",
                            (_DIGEST_CHANNEL_OUTAGE_KEY,),
                        )
                conn.commit()
                return recovery_created
            except Exception:
                conn.rollback()
                raise

    def get_runtime_state(self, key: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT value FROM attention_runtime_state WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"raw": row["value"]}
        return value if isinstance(value, dict) else {"value": value}

    def inventory_rows(self) -> list[dict[str, Any]]:
        """Return metadata-only inventory joined with the active reminder."""

        with self._lock, closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT t.*, r.due_local_date AS reminder_due_local_date,
                       r.days AS reminder_days, r.set_at AS reminder_set_at,
                       r.active AS reminder_active
                  FROM attention_threads t
             LEFT JOIN attention_reminders r ON r.thread_id=t.thread_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT * FROM attention_threads WHERE thread_id=?",
                (thread_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_outbox(self, logical_key: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT * FROM attention_outbox WHERE logical_key=?",
                (logical_key,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result
