from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from thread_attention.commands import parse_command
from thread_attention.database import quick_check
from thread_attention.repository import AttentionRepository


UTC = timezone.utc
NOW = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="thread-attention-repo-")
        self.path = Path(self.temp.name) / "relations.sqlite3"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE relations (
                    guild_id TEXT, thread_id TEXT, related_thread_id TEXT,
                    relation TEXT, label TEXT, created_at TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO relations VALUES ('g', 'a', 'b', 'related', NULL, 'now')"
            )
        self.repo = AttentionRepository(self.path)
        self.repo.migrate()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _command(self, text: str, message_id: str, due: date | None = None, **kwargs):
        return self.repo.process_command(
            attempt=parse_command(text),
            source_message_id=message_id,
            thread_id="thread-1",
            scope_id="guild-1",
            target_channel_id="thread-1",
            observed_at=NOW,
            due_local_date=due,
            **kwargs,
        )

    def test_migration_is_additive_and_integrity_checked(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0], 1)
            version = conn.execute(
                "SELECT value FROM attention_schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
        self.assertEqual(version, "1")
        self.assertEqual(quick_check(self.path), "ok")

    def test_reminder_command_commits_state_exclusion_and_outbox_once(self) -> None:
        result = self._command("!ㄱ 30ㅇ", "message-1", date(2026, 9, 29))
        duplicate = self._command("!ㄱ 30ㅇ", "message-1", date(2027, 1, 1))
        self.assertEqual(result.outcome_code, "reminder_set")
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(duplicate.due_local_date, "2026-09-29")
        self.assertTrue(self.repo.has_history_exclusion("message-1"))
        thread = self.repo.get_thread("thread-1")
        self.assertIsNone(thread["closed_at"])
        outbox = self.repo.get_outbox("command:message-1")
        self.assertEqual(outbox["payload"]["days"], 30)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM attention_command_receipts"
                ).fetchone()[0],
                1,
            )

    def test_close_cancels_reminder_and_seen_reopens_without_changing_it(self) -> None:
        self._command("!r 30d", "message-1", date(2026, 9, 29))
        self._command("!c", "message-2")
        with closing(sqlite3.connect(self.path)) as conn, conn:
            self.assertEqual(
                conn.execute(
                    "SELECT active FROM attention_reminders WHERE thread_id='thread-1'"
                ).fetchone()[0],
                0,
            )
        self.assertIsNotNone(self.repo.get_thread("thread-1")["closed_at"])

        # A later explicit reminder reopens, and !s leaves that active reminder alone.
        later = datetime(2026, 8, 31, tzinfo=UTC)
        self.repo.process_command(
            attempt=parse_command("!r 7d"),
            source_message_id="message-3",
            thread_id="thread-1",
            scope_id="guild-1",
            target_channel_id="thread-1",
            observed_at=later,
            due_local_date=date(2026, 9, 7),
        )
        self.repo.process_command(
            attempt=parse_command("!s"),
            source_message_id="message-4",
            thread_id="thread-1",
            scope_id="guild-1",
            target_channel_id="thread-1",
            observed_at=later,
        )
        self.assertIsNone(self.repo.get_thread("thread-1")["closed_at"])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            self.assertEqual(
                conn.execute(
                    "SELECT active, due_local_date FROM attention_reminders WHERE thread_id='thread-1'"
                ).fetchone(),
                (1, "2026-09-07"),
            )

    def test_invalid_and_configuration_error_do_not_create_inventory(self) -> None:
        invalid = self._command("!r 0d", "bad-1")
        configured = self._command(
            "!s", "bad-2", forced_outcome="config_error"
        )
        self.assertEqual(invalid.outcome_code, "reminder_range")
        self.assertEqual(configured.outcome_code, "config_error")
        self.assertIsNone(self.repo.get_thread("thread-1"))
        self.assertTrue(self.repo.has_history_exclusion("bad-1"))
        self.assertTrue(self.repo.has_history_exclusion("bad-2"))

    def test_cancel_without_reminder_does_not_create_inventory(self) -> None:
        result = self._command("!r -", "cancel-1")
        self.assertEqual(result.outcome_code, "reminder_already_clear")
        self.assertIsNone(self.repo.get_thread("thread-1"))

    def test_outbox_retry_schedule_and_confirmation_ids(self) -> None:
        self._command("!s", "message-1")
        item = self.repo.claim_due_outbox(observed_at=NOW)
        self.assertEqual(item.attempts, 1)
        self.repo.mark_outbox_failed(
            item.id,
            attempts=item.attempts,
            error_code="transient",
            observed_at=NOW,
        )
        outbox = self.repo.get_outbox("command:message-1")
        self.assertIn("00:01:00", outbox["next_attempt_at"])

        retry_now = datetime(2026, 8, 30, 0, 1, tzinfo=UTC)
        retry = self.repo.claim_due_outbox(observed_at=retry_now)
        self.assertEqual(retry.attempts, 2)
        self.repo.mark_outbox_delivered(
            retry.id,
            message_ids=("confirmation-1", "confirmation-2"),
            observed_at=retry_now,
        )
        self.assertTrue(self.repo.has_history_exclusion("confirmation-1"))
        self.assertTrue(self.repo.has_history_exclusion("confirmation-2"))

    def test_permanent_source_failure_atomically_enqueues_minimal_warning(self) -> None:
        self._command("!s", "message-warning")
        item = self.repo.claim_due_outbox(observed_at=NOW)
        self.assertIsNotNone(item)

        self.assertTrue(
            self.repo.abandon_source_confirmation_and_warn(
                item.id,
                error_code="not_found",
                digest_channel_id="review-channel",
                observed_at=NOW,
            )
        )

        source = self.repo.get_outbox("command:message-warning")
        warning = self.repo.get_outbox(f"source-warning:{item.id}")
        self.assertEqual(source["status"], "abandoned")
        self.assertEqual(warning["kind"], "source_warning")
        self.assertEqual(warning["target_channel_id"], "review-channel")
        self.assertEqual(
            warning["payload"],
            {
                "thread_id": "thread-1",
                "scope_id": "guild-1",
                "applied": True,
                "error_code": "not_found",
            },
        )

    def test_digest_channel_outage_is_deduplicated_and_recovery_is_enqueued_once(self) -> None:
        activation = self.repo.ensure_activation([], observed_at=NOW)
        self.repo.complete_activation_if_ready(
            activation_id=activation,
            digest_channel_id="review-channel",
            observed_at=NOW,
        )
        summary = self.repo.claim_due_outbox(observed_at=NOW)
        self.assertEqual(summary.kind, "initial_summary")
        self.assertTrue(
            self.repo.mark_outbox_failed(
                summary.id,
                attempts=summary.attempts,
                error_code="forbidden",
                observed_at=NOW,
                record_digest_outage=True,
            )
        )

        self.repo.ensure_digest_outbox(
            local_date=date(2026, 8, 30),
            digest_channel_id="review-channel",
            observed_at=NOW,
        )
        digest = self.repo.claim_due_outbox(observed_at=NOW)
        self.assertEqual(digest.kind, "digest")
        self.assertFalse(
            self.repo.mark_outbox_failed(
                digest.id,
                attempts=digest.attempts,
                error_code="forbidden",
                observed_at=NOW,
                record_digest_outage=True,
            )
        )
        self.assertEqual(
            self.repo.get_runtime_state("digest_channel_outage")["started_at"],
            NOW.isoformat(),
        )

        recovered_at = NOW + timedelta(minutes=1)
        retry = self.repo.claim_due_outbox(observed_at=recovered_at)
        self.assertEqual(retry.kind, "initial_summary")
        self.assertTrue(
            self.repo.mark_outbox_delivered(
                retry.id,
                observed_at=recovered_at,
                digest_channel_id="review-channel",
            )
        )
        self.assertIsNone(self.repo.get_runtime_state("digest_channel_outage"))
        recovery = self.repo.get_outbox(
            f"channel-recovery:{NOW.isoformat()}"
        )
        self.assertEqual(recovery["kind"], "channel_recovery")
        self.assertEqual(recovery["payload"]["started_at"], NOW.isoformat())
        self.assertEqual(recovery["payload"]["recovered_at"], recovered_at.isoformat())

    def test_activation_snapshot_resumes_and_enqueues_one_summary(self) -> None:
        activation = self.repo.ensure_activation(["3", "1", "2"], observed_at=NOW)
        same = self.repo.ensure_activation(["new"], observed_at=NOW)
        self.assertEqual(activation, same)
        self.assertEqual(self.repo.pending_backfill(activation), ["1", "2", "3"])
        for thread_id in ("1", "2"):
            self.repo.record_backfill_result(
                activation_id=activation,
                thread_id=thread_id,
                metadata={
                    "accessible": True,
                    "scope_id": "guild",
                    "thread_name": f"Thread {thread_id}",
                    "last_activity_at": NOW,
                },
                local_date=date(2026, 8, 30),
                observed_at=NOW,
            )
        self.repo.record_backfill_result(
            activation_id=activation,
            thread_id="3",
            metadata={"accessible": False},
            local_date=date(2026, 8, 30),
            observed_at=NOW,
        )
        self.assertTrue(
            self.repo.complete_activation_if_ready(
                activation_id=activation,
                digest_channel_id="review-channel",
                observed_at=NOW,
            )
        )
        self.assertFalse(
            self.repo.complete_activation_if_ready(
                activation_id=activation,
                digest_channel_id="review-channel",
                observed_at=NOW,
            )
        )
        summary = self.repo.get_outbox(f"initial:{activation}")
        self.assertEqual(summary["payload"], {"total": 3, "accessible": 2, "inaccessible": 1})

    def test_reenable_reconciles_ids_without_reopening_initial_snapshot(self) -> None:
        activation = self.repo.ensure_activation(["old"], observed_at=NOW)
        self.repo.record_backfill_result(
            activation_id=activation,
            thread_id="old",
            metadata={"accessible": False},
            local_date=date(2026, 8, 30),
            observed_at=NOW,
        )
        self.repo.complete_activation_if_ready(
            activation_id=activation,
            digest_channel_id="review-channel",
            observed_at=NOW,
        )

        later = NOW + timedelta(days=2)
        self.repo.reconcile_participation_ids(
            ["old", "while-disabled"],
            observed_at=later,
        )

        self.assertEqual(self.repo.activation_status(activation), "ready")
        self.assertEqual(self.repo.pending_backfill(activation), [])
        self.assertEqual(self.repo.get_thread("old")["historical"], 1)
        missed = self.repo.get_thread("while-disabled")
        self.assertEqual(missed["historical"], 0)
        self.assertEqual(missed["registration_source"], "live")
        self.assertEqual(missed["link_state"], "unknown")

    def test_unknown_live_thread_is_resolved_and_inaccessible_rechecks_back_off(self) -> None:
        self.repo.record_thread_participation("live-1", observed_at=NOW)
        self.assertEqual(
            self.repo.metadata_refresh_thread_ids(local_date=date(2026, 8, 30)),
            ["live-1"],
        )
        self.repo.record_metadata_result(
            thread_id="live-1",
            metadata={"accessible": False},
            local_date=date(2026, 8, 30),
            observed_at=NOW,
        )
        self.assertEqual(
            self.repo.get_thread("live-1")["next_access_check_date"],
            "2026-08-31",
        )
        # The seventh local-date check changes from daily to weekly.
        self.repo.record_metadata_result(
            thread_id="live-1",
            metadata={"accessible": False},
            local_date=date(2026, 9, 5),
            observed_at=datetime(2026, 9, 5, tzinfo=UTC),
        )
        self.assertEqual(
            self.repo.get_thread("live-1")["next_access_check_date"],
            "2026-09-12",
        )
        self.repo.record_metadata_result(
            thread_id="live-1",
            metadata={
                "accessible": True,
                "scope_id": "guild",
                "parent_channel_id": "parent",
                "thread_name": "Recovered",
                "last_discord_activity_at": datetime(2026, 9, 5, tzinfo=UTC),
                "last_hermes_activity_at": datetime(2026, 9, 4, tzinfo=UTC),
                "archived": True,
                "auto_archive_minutes": 10080,
                "archive_at": datetime(2026, 9, 5, tzinfo=UTC),
            },
            local_date=date(2026, 9, 12),
            observed_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
        recovered = self.repo.get_thread("live-1")
        self.assertEqual(recovered["link_state"], "accessible")
        self.assertIsNone(recovered["next_access_check_date"])
        self.assertEqual(recovered["thread_name"], "Recovered")

    def test_backfill_cannot_roll_back_newer_live_activity(self) -> None:
        activation = self.repo.ensure_activation(["race"], observed_at=NOW)
        newer = datetime(2026, 9, 1, tzinfo=UTC)
        self.repo.record_hermes_activity(
            thread_id="race",
            message_id="new-message",
            observed_at=newer,
            scope_id="guild",
            parent_channel_id="parent",
            thread_name="Race",
        )
        self.repo.record_backfill_result(
            activation_id=activation,
            thread_id="race",
            metadata={
                "accessible": True,
                "scope_id": "guild",
                "last_discord_activity_at": NOW,
                "last_hermes_activity_at": NOW,
            },
            local_date=date(2026, 9, 1),
            observed_at=newer,
        )

        thread = self.repo.get_thread("race")
        self.assertEqual(thread["last_hermes_activity_at"], newer.isoformat())
        self.assertEqual(thread["last_hermes_message_id"], "new-message")

    def test_older_interaction_does_not_acknowledge_future_hermes_activity(self) -> None:
        future = datetime(2026, 9, 1, tzinfo=UTC)
        self.repo.record_hermes_activity(
            thread_id="thread-1",
            message_id="future-message",
            observed_at=future,
            scope_id="guild-1",
            parent_channel_id="parent",
            thread_name="Future",
        )
        self.repo.record_user_interaction(
            thread_id="thread-1",
            message_id="older-user-message",
            observed_at=NOW,
            scope_id="guild-1",
            parent_channel_id="parent",
            thread_name="Future",
        )

        thread = self.repo.get_thread("thread-1")
        self.assertEqual(thread["acknowledged_at"], NOW.isoformat())
        self.assertIsNone(thread["acknowledged_message_id"])
        self.assertEqual(thread["last_hermes_activity_at"], future.isoformat())

    def test_accessible_metadata_becomes_refreshable_next_local_day(self) -> None:
        self.repo.record_thread_participation("daily", observed_at=NOW)
        self.repo.record_metadata_result(
            thread_id="daily",
            metadata={
                "accessible": True,
                "scope_id": "guild",
                "last_hermes_activity_at": NOW,
            },
            local_date=date(2026, 8, 30),
            observed_at=NOW,
        )
        same_day_cutoff = datetime(2026, 8, 29, 15, 0, tzinfo=UTC)
        next_day_cutoff = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)
        self.assertNotIn(
            "daily",
            self.repo.metadata_refresh_thread_ids(
                local_date=date(2026, 8, 30),
                accessible_checked_before=same_day_cutoff,
            ),
        )
        self.assertIn(
            "daily",
            self.repo.metadata_refresh_thread_ids(
                local_date=date(2026, 8, 31),
                accessible_checked_before=next_day_cutoff,
            ),
        )


if __name__ == "__main__":
    unittest.main()
