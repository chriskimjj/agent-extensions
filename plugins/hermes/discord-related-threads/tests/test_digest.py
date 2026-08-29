from __future__ import annotations

import unittest
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from thread_attention.digest import render_digest, select_digest


UTC = timezone.utc
SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)  # 09:00 Asia/Seoul


def row(thread_id: str, **overrides):
    value = {
        "thread_id": thread_id,
        "scope_id": "guild-1",
        "thread_name": f"Thread {thread_id}",
        "closed_at": None,
        "link_state": "accessible",
        "last_hermes_activity_at": "2026-08-27T00:00:00+00:00",
        "acknowledged_at": None,
        "last_user_interaction_at": None,
        "last_exposed_at": None,
        "archive_at": None,
        "historical": 0,
        "reminder_active": 0,
        "reminder_due_local_date": None,
        "reminder_set_at": None,
    }
    value.update(overrides)
    return value


class DigestSelectionTest(unittest.TestCase):
    def select(self, rows):
        return select_digest(
            rows,
            now=NOW,
            digest_time=time(9, 0),
            timezone_info=SEOUL,
        )

    def test_three_local_days_makes_unseen_thread_due(self) -> None:
        selection = self.select([row("1")])
        self.assertEqual(len(selection.items), 1)
        self.assertEqual(selection.items[0].reasons, ("미확인",))

    def test_acknowledged_activity_is_suppressed_until_new_hermes_activity(self) -> None:
        quiet = row("1", acknowledged_at="2026-08-27T00:00:00+00:00")
        self.assertEqual(self.select([quiet]).items, ())
        active = row(
            "1",
            acknowledged_at="2026-08-26T00:00:00+00:00",
            last_user_interaction_at="2026-08-26T01:00:00+00:00",
        )
        self.assertEqual(self.select([active]).items[0].reasons, ("새 활동",))

    def test_due_reminder_merges_with_automatic_reason(self) -> None:
        selection = self.select(
            [
                row(
                    "1",
                    reminder_active=1,
                    reminder_due_local_date="2026-08-30",
                    reminder_set_at="2026-08-20T00:00:00+00:00",
                )
            ]
        )
        self.assertEqual(selection.items[0].reasons, ("미확인", "재알림"))

    def test_three_day_reexposure_limit_and_new_explicit_reminder_override(self) -> None:
        cooling = row("1", last_exposed_at="2026-08-29T00:00:00+00:00")
        self.assertEqual(self.select([cooling]).items, ())
        explicit = row(
            "1",
            last_exposed_at="2026-08-29T00:00:00+00:00",
            reminder_active=1,
            reminder_due_local_date="2026-08-30",
            reminder_set_at="2026-08-29T01:00:00+00:00",
        )
        self.assertEqual(self.select([explicit]).items[0].reasons, ("재알림",))

    def test_five_plus_five_and_new_three_historical_two(self) -> None:
        rows = []
        for index in range(8):
            rows.append(
                row(
                    f"r-{index}",
                    reminder_active=1,
                    reminder_due_local_date="2026-08-30",
                    reminder_set_at="2026-08-20T00:00:00+00:00",
                )
            )
        for index in range(5):
            rows.append(row(f"new-{index}"))
        for index in range(3):
            rows.append(row(f"old-{index}", historical=1))
        selection = self.select(rows)
        self.assertEqual(len(selection.items), 10)
        self.assertEqual(selection.outside_count, 6)
        reminder_count = sum(item.has_reminder for item in selection.items)
        historical_auto = sum(
            item.historical and not item.has_reminder for item in selection.items
        )
        self.assertEqual(reminder_count, 5)
        self.assertEqual(historical_auto, 2)

    def test_unused_half_is_borrowed(self) -> None:
        rows = [row(f"a-{index}") for index in range(10)]
        selection = self.select(rows)
        self.assertEqual(len(selection.items), 10)

    def test_inaccessible_closed_and_not_yet_due_are_not_counted(self) -> None:
        selection = self.select(
            [
                row("inaccessible", link_state="inaccessible"),
                row("closed", closed_at="2026-08-20T00:00:00+00:00"),
                row("future", last_hermes_activity_at="2026-08-29T00:00:00+00:00"),
            ]
        )
        self.assertEqual(selection.total_candidates, 0)

    def test_empty_and_nonempty_rendering(self) -> None:
        empty = self.select([])
        self.assertEqual(
            render_digest(empty, now=NOW, timezone_info=SEOUL),
            "Hermes 검토 · 2026-08-30\n오늘 다시 볼 쓰레드는 0개입니다.",
        )
        selection = self.select([row("1", thread_name="A [long] name")])
        rendered = render_digest(selection, now=NOW, timezone_info=SEOUL)
        self.assertIn("표시 1개", rendered)
        self.assertIn("https://discord.com/channels/guild-1/1", rendered)
        self.assertNotIn("외 0개", rendered)


if __name__ == "__main__":
    unittest.main()
