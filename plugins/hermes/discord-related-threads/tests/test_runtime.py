from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

from thread_attention.commands import COMMAND_LIST
from thread_attention.config import ThreadAttentionConfig
from thread_attention.repository import AttentionRepository
from thread_attention.runtime import ThreadAttentionRuntime


UTC = timezone.utc
NOW = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)


class FakeRawMessage:
    def __init__(self) -> None:
        self.reactions: list[str] = []
        self.guild = SimpleNamespace(me=SimpleNamespace(id="bot"))

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)

    async def remove_reaction(self, emoji: str, _member) -> None:
        if emoji in self.reactions:
            self.reactions.remove(emoji)


class FakeAdapter:
    def __init__(self, thread_ids=(), results=()) -> None:
        self.thread_ids = tuple(thread_ids)
        self.results = list(results)
        self.sent: list[dict] = []
        self.metadata_calls: list[tuple[str, bool]] = []
        self._next_id = 100

    async def validate_delivery_target(self, channel_id: str):
        return {"ok": channel_id == "999"}

    def participating_thread_ids(self):
        return self.thread_ids

    async def resolve_thread_metadata(
        self, thread_id: str, *, include_activity_history: bool = True
    ):
        self.metadata_calls.append((thread_id, include_activity_history))
        if thread_id == "gone":
            return {"accessible": False}
        return {
            "accessible": True,
            "scope_id": "guild-1",
            "parent_channel_id": "parent-1",
            "thread_name": f"Thread {thread_id}",
            "last_activity_at": datetime(2026, 8, 27, 0, 0, tzinfo=UTC),
            "archived": False,
            "auto_archive_minutes": 10080,
            "archive_at": datetime(2026, 9, 3, 0, 0, tzinfo=UTC),
        }

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self._next_id += 1
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return SimpleNamespace(
            success=True,
            message_id=str(self._next_id),
            continuation_message_ids=(),
            raw_response=None,
        )


class FakeNativeBot:
    def __init__(self) -> None:
        self.user = SimpleNamespace(id="bot-user")
        self.listeners: dict[str, list] = {}

    def add_listener(self, callback, name: str) -> None:
        self.listeners.setdefault(name, []).append(callback)

    def remove_listener(self, callback, name: str) -> None:
        self.listeners.get(name, []).remove(callback)


def make_event(text: str, message_id: str = "m1"):
    raw = FakeRawMessage()
    source = SimpleNamespace(
        platform="discord",
        chat_type="thread",
        chat_id="thread-1",
        thread_id="thread-1",
        scope_id="guild-1",
        guild_id="guild-1",
        parent_chat_id="parent-1",
        chat_name="Work thread",
        message_id=message_id,
        is_bot=False,
    )
    return SimpleNamespace(
        text=text,
        message_id=message_id,
        timestamp=NOW,
        source=source,
        raw_message=raw,
    )


class RuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="thread-attention-runtime-")
        repo = AttentionRepository(Path(self.temp.name) / "relations.sqlite3")
        config = ThreadAttentionConfig(
            enabled=True,
            digest_channel_id="999",
            digest_time=time(9, 0),
            timezone_name="Asia/Seoul",
        )
        self.runtime = ThreadAttentionRuntime(config, repository=repo, clock=lambda: NOW)
        self.adapter = FakeAdapter()

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()
        self.temp.cleanup()

    async def test_authorized_command_is_skipped_and_delivered_without_llm(self) -> None:
        self.runtime.state = "active"
        event = make_event("!ㄱ 30ㅇ")
        result = self.runtime.on_pre_gateway_dispatch(
            event=event,
            adapter=self.adapter,
            is_authorized=True,
        )
        self.assertEqual(result["action"], "skip")

        for _ in range(100):
            if self.adapter.sent:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(self.adapter.sent), 1)
        sent = self.adapter.sent[0]
        self.assertEqual(sent["chat_id"], "thread-1")
        self.assertEqual(sent["reply_to"], "m1")
        self.assertIn("!ㄱ 30ㅇ → 30일 뒤(2026-09-29 09:00)", sent["content"])
        self.assertEqual(sent["content"].splitlines()[-1], COMMAND_LIST)
        self.assertTrue(sent["metadata"]["non_conversational"])
        self.assertTrue(self.runtime.repository.has_history_exclusion("m1"))
        self.assertIn("✅", event.raw_message.reactions)
        self.assertNotIn("⏳", event.raw_message.reactions)

    async def test_unauthorized_command_is_not_consumed_or_recorded(self) -> None:
        self.runtime.state = "active"
        event = make_event("!c")
        self.assertIsNone(
            self.runtime.on_pre_gateway_dispatch(
                event=event,
                adapter=self.adapter,
                is_authorized=False,
            )
        )
        self.assertFalse(self.runtime.repository.has_history_exclusion("m1"))
        self.assertEqual(self.adapter.sent, [])

    async def test_ordinary_prompt_advances_interaction_and_stays_on_agent_path(self) -> None:
        self.runtime.state = "active"
        event = make_event("e")
        self.assertIsNone(
            self.runtime.on_pre_gateway_dispatch(
                event=event,
                adapter=self.adapter,
                is_authorized=True,
            )
        )
        thread = self.runtime.repository.get_thread("thread-1")
        self.assertIsNotNone(thread["last_user_interaction_at"])
        self.assertEqual(self.adapter.sent, [])

    async def test_history_fallback_requires_self_template_or_authorized_thread_command(self) -> None:
        self.assertTrue(
            self.runtime.on_history_message(
                platform="discord",
                message_id="unknown",
                content="!c",
                chat_type="thread",
                author_is_authorized=True,
                author_is_self=False,
            )
        )
        self.assertFalse(
            self.runtime.on_history_message(
                platform="discord",
                message_id="unknown",
                content="!c",
                chat_type="thread",
                author_is_authorized=False,
                author_is_self=False,
            )
        )
        confirmation = "✅ 종료됨\n" + COMMAND_LIST
        self.assertTrue(
            self.runtime.on_history_message(
                platform="discord",
                message_id="unknown",
                content=confirmation,
                chat_type="thread",
                author_is_authorized=None,
                author_is_self=True,
            )
        )

    async def test_recognized_command_bypasses_discord_batching_even_while_starting(self) -> None:
        event = make_event("!c")
        self.assertTrue(
            self.runtime.on_control_message(platform="discord", event=event)
        )
        event.text = "ordinary prompt"
        self.assertFalse(
            self.runtime.on_control_message(platform="discord", event=event)
        )

    async def test_permanent_source_failure_routes_warning_to_review_channel(self) -> None:
        failure = SimpleNamespace(success=False, error_kind="not_found")
        self.adapter = FakeAdapter(results=(failure,))
        self.runtime.state = "active"
        event = make_event("!s", message_id="warn-command")

        self.runtime.on_pre_gateway_dispatch(
            event=event,
            adapter=self.adapter,
            is_authorized=True,
        )
        for _ in range(100):
            if len(self.adapter.sent) >= 2:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(len(self.adapter.sent), 2)
        warning = self.adapter.sent[1]
        self.assertEqual(warning["chat_id"], "999")
        self.assertIsNone(warning["reply_to"])
        self.assertNotIn("thread_id", warning["metadata"])
        self.assertIn("명령 확인 전달 중단 · 장부 적용 성공", warning["content"])
        self.assertIn("/guild-1/thread-1", warning["content"])

    async def test_live_metadata_refresh_skips_historical_message_scan(self) -> None:
        self.runtime.state = "active"
        self.runtime._adapter = self.adapter
        self.runtime.repository.record_thread_participation(
            "fresh", observed_at=NOW
        )

        self.assertTrue(await self.runtime._refresh_metadata_batch())
        self.assertIn(("fresh", False), self.adapter.metadata_calls)

    async def test_stock_discord_listener_records_self_delivery_only(self) -> None:
        native = FakeNativeBot()
        self.runtime.state = "active"
        self.runtime.on_discord_connected(native=native, adapter=self.adapter)

        channel = SimpleNamespace(
            id="thread-native",
            parent_id="parent-native",
            name="Native thread",
            guild=SimpleNamespace(id="guild-native"),
        )
        ordinary = SimpleNamespace(
            id="native-message",
            author=SimpleNamespace(id="bot-user"),
            channel=channel,
            guild=channel.guild,
            content="ordinary Hermes response",
            created_at=NOW,
        )
        confirmation = SimpleNamespace(
            id="native-confirmation",
            author=SimpleNamespace(id="bot-user"),
            channel=channel,
            guild=channel.guild,
            content="✅ 종료됨\n" + COMMAND_LIST,
            created_at=NOW,
        )

        self.runtime.on_native_discord_message(ordinary)
        self.runtime.on_native_discord_message(confirmation)
        self.runtime.on_native_discord_thread_create(
            SimpleNamespace(
                id="thread-created",
                parent_id="parent-native",
                name="Created by Hermes",
                guild=channel.guild,
                owner_id="bot-user",
                created_at=NOW,
            )
        )

        row = self.runtime.repository.get_thread("thread-native")
        self.assertEqual(row["last_hermes_message_id"], "native-message")
        created = self.runtime.repository.get_thread("thread-created")
        self.assertEqual(created["thread_name"], "Created by Hermes")
        self.assertEqual(set(native.listeners), {
            "on_message",
            "on_thread_create",
        })
        self.runtime.on_unload()
        self.assertTrue(all(not callbacks for callbacks in native.listeners.values()))

    async def test_missing_public_adapter_contract_refuses_activation(self) -> None:
        class IncompleteAdapter:
            async def send(self, *_args, **_kwargs):
                return None

        self.runtime._adapter = IncompleteAdapter()
        self.assertFalse(await self.runtime._activate_if_possible())
        self.assertEqual(self.runtime.state, "compatibility_error")
        self.assertIn("participating_thread_ids", self.runtime.state_error)

    async def test_missing_hook_contract_refuses_activation_and_drops_command(self) -> None:
        repo = AttentionRepository(Path(self.temp.name) / "incompatible.sqlite3")
        runtime = ThreadAttentionRuntime(
            self.runtime.config,
            repository=repo,
            clock=lambda: NOW,
            host_contract_error="unsupported Hermes plugin host",
        )
        self.assertEqual(runtime.state, "compatibility_error")
        result = runtime.on_pre_gateway_dispatch(
            event=make_event("!c"),
            adapter=self.adapter,
            is_authorized=False,
        )
        self.assertEqual(result["action"], "skip")
        self.assertEqual(self.adapter.sent, [])

    async def test_digest_outage_recovery_emits_one_fixed_notice(self) -> None:
        failure = SimpleNamespace(success=False, error_kind="forbidden")
        self.adapter = FakeAdapter(results=(failure,))
        self.runtime._adapter = self.adapter
        self.runtime.repository.ensure_digest_outbox(
            local_date=date(2026, 8, 30),
            digest_channel_id="999",
            observed_at=NOW,
        )
        digest = self.runtime.repository.claim_due_outbox(observed_at=NOW)
        await self.runtime._deliver(digest)
        self.assertIsNotNone(
            self.runtime.repository.get_runtime_state("digest_channel_outage")
        )

        activation = self.runtime.repository.ensure_activation([], observed_at=NOW)
        self.runtime.repository.complete_activation_if_ready(
            activation_id=activation,
            digest_channel_id="999",
            observed_at=NOW,
        )
        summary = self.runtime.repository.claim_due_outbox(observed_at=NOW)
        self.assertEqual(summary.kind, "initial_summary")
        await self.runtime._deliver(summary)
        recovery = self.runtime.repository.claim_due_outbox(observed_at=NOW)
        self.assertEqual(recovery.kind, "channel_recovery")
        await self.runtime._deliver(recovery)

        notices = [
            sent["content"]
            for sent in self.adapter.sent
            if "검토 채널 전달 복구" in sent["content"]
        ]
        self.assertEqual(len(notices), 1)
        self.assertIn("중단 2026-08-30 09:00", notices[0])
        self.assertIn("복구 2026-08-30 09:00", notices[0])
        self.assertIsNone(
            self.runtime.repository.get_runtime_state("digest_channel_outage")
        )

    async def test_startup_snapshots_backfill_and_sends_summary_plus_digest(self) -> None:
        self.adapter = FakeAdapter(("old", "gone"))
        self.runtime.on_discord_connected(
            native=FakeNativeBot(),
            adapter=self.adapter,
        )
        for _ in range(200):
            activation = self.runtime._activation_id
            if (
                activation
                and self.runtime.repository.activation_status(activation) == "ready"
                and len(self.adapter.sent) >= 2
            ):
                break
            await asyncio.sleep(0.01)
        activation = self.runtime._activation_id
        self.assertEqual(self.runtime.repository.activation_status(activation), "ready")
        self.assertEqual(self.runtime.repository.get_thread("old")["historical"], 1)
        self.assertEqual(
            self.runtime.repository.get_thread("gone")["link_state"],
            "inaccessible",
        )
        contents = "\n".join(item["content"] for item in self.adapter.sent)
        self.assertIn("초기 가져오기: 총 2개", contents)
        self.assertIn("Hermes 검토 · 2026-08-30", contents)
        self.assertTrue(all(item["chat_id"] == "999" for item in self.adapter.sent))


if __name__ == "__main__":
    unittest.main()
