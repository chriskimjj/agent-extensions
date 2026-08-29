from __future__ import annotations

import unittest

from thread_attention.commands import (
    COMMAND_LIST,
    CommandAction,
    is_confirmation_template,
    parse_command,
    render_confirmation,
)
from thread_attention.config import parse_thread_attention_config


def feature_config(**values):
    return {
        "plugins": {
            "entries": {
                "discord-related-threads": {"thread_attention": values}
            }
        }
    }


class CommandParserTest(unittest.TestCase):
    def test_unrelated_bang_message_is_not_owned(self) -> None:
        self.assertIsNone(parse_command("!hello"))
        self.assertIsNone(parse_command("e"))

    def test_seen_and_close_aliases_are_case_insensitive(self) -> None:
        for text, action in (
            ("!s", CommandAction.SEEN),
            (" !S ", CommandAction.SEEN),
            ("!ㄴ", CommandAction.SEEN),
            ("!c", CommandAction.CLOSE),
            ("!C", CommandAction.CLOSE),
            ("!ㅊ", CommandAction.CLOSE),
        ):
            with self.subTest(text=text):
                attempt = parse_command(text)
                self.assertIsNotNone(attempt)
                self.assertTrue(attempt.valid)
                self.assertEqual(attempt.action, action)

    def test_reminder_accepts_all_english_korean_key_mixes(self) -> None:
        for text in ("!r 30d", "!ㄱ 30d", "!r 30ㅇ", "!ㄱ 30ㅇ", "!R 30D"):
            with self.subTest(text=text):
                attempt = parse_command(text)
                self.assertIsNotNone(attempt)
                self.assertTrue(attempt.valid)
                self.assertEqual(attempt.action, CommandAction.REMIND)
                self.assertEqual(attempt.days, 30)

    def test_reminder_range_is_one_through_3650(self) -> None:
        self.assertTrue(parse_command("!r 1d").valid)
        self.assertTrue(parse_command("!r 3650d").valid)
        self.assertEqual(parse_command("!r 0d").error_code, "reminder_range")
        self.assertEqual(parse_command("!r 3651d").error_code, "reminder_range")

    def test_known_first_token_is_recognized_even_with_bad_arguments(self) -> None:
        for text in ("!s extra", "!c now", "!r", "!r 30ㄷ", "!ㄱ x y"):
            with self.subTest(text=text):
                attempt = parse_command(text)
                self.assertIsNotNone(attempt)
                self.assertTrue(attempt.recognized)
                self.assertFalse(attempt.valid)

    def test_cancel_aliases(self) -> None:
        for text in ("!r -", "!R -", "!ㄱ -"):
            attempt = parse_command(text)
            self.assertTrue(attempt.valid)
            self.assertEqual(attempt.action, CommandAction.CANCEL_REMINDER)

    def test_confirmation_is_two_deterministic_lines(self) -> None:
        rendered = render_confirmation(
            outcome_code="reminder_set",
            command="!ㄱ",
            days=30,
            due_date="2026-09-29",
            digest_time_label="09:00",
        )
        self.assertEqual(rendered.splitlines()[-1], COMMAND_LIST)
        self.assertIn("30일 뒤(2026-09-29 09:00)", rendered)
        self.assertTrue(is_confirmation_template(rendered))
        self.assertFalse(is_confirmation_template("✅ ordinary answer\n" + COMMAND_LIST))


class ConfigParserTest(unittest.TestCase):
    def test_feature_is_disabled_by_default(self) -> None:
        parsed = parse_thread_attention_config({})
        self.assertFalse(parsed.enabled)
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.digest_time_label, "09:00")
        self.assertEqual(parsed.timezone_name, "Asia/Seoul")

    def test_explicit_valid_configuration(self) -> None:
        parsed = parse_thread_attention_config(
            feature_config(
                enabled=True,
                digest_channel_id="123456789012345678",
                digest_time="07:35",
                timezone="America/New_York",
            )
        )
        self.assertTrue(parsed.enabled)
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.digest_channel_id, "123456789012345678")
        self.assertEqual(parsed.digest_time_label, "07:35")
        self.assertEqual(parsed.timezone_name, "America/New_York")

    def test_enabled_configuration_is_strict(self) -> None:
        parsed = parse_thread_attention_config(
            feature_config(
                enabled=True,
                digest_channel_id=123,
                digest_time="25:00",
                timezone="Mars/Olympus",
            )
        )
        self.assertTrue(parsed.enabled)
        self.assertFalse(parsed.valid)
        self.assertEqual(len(parsed.errors), 3)


if __name__ == "__main__":
    unittest.main()
