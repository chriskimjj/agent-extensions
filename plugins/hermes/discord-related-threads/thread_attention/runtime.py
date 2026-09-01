"""Hermes/Discord runtime wiring for the thread-attention domain."""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .commands import (
    CommandAction,
    is_confirmation_template,
    parse_command,
    render_confirmation,
)
from .config import ThreadAttentionConfig
from .digest import render_digest, select_digest
from .repository import AttentionRepository, OutboxItem, as_utc, utc_now


logger = logging.getLogger("hermes.plugins.discord-related-threads.thread-attention")
UTC = timezone.utc


def _platform_name(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").lower()


def _event_time(event: object) -> datetime:
    value = getattr(event, "timestamp", None)
    return as_utc(value if isinstance(value, datetime) else None)


def _source_fields(event: object) -> dict[str, str | None]:
    source = getattr(event, "source", None)
    thread_id = getattr(source, "thread_id", None)
    if not thread_id and getattr(source, "chat_type", None) == "thread":
        thread_id = getattr(source, "chat_id", None)
    return {
        "thread_id": str(thread_id) if thread_id else None,
        "scope_id": str(
            getattr(source, "scope_id", None)
            or getattr(source, "guild_id", None)
            or ""
        )
        or None,
        "parent_channel_id": str(getattr(source, "parent_chat_id", None) or "")
        or None,
        "thread_name": str(getattr(source, "chat_name", None) or "") or None,
        "message_id": str(
            getattr(event, "message_id", None)
            or getattr(source, "message_id", None)
            or ""
        )
        or None,
    }


class ThreadAttentionRuntime:
    """One profile's feature state and background worker."""

    def __init__(
        self,
        config: ThreadAttentionConfig,
        *,
        repository: AttentionRepository | None = None,
        clock=utc_now,
        host_contract_error: str | None = None,
    ) -> None:
        self.config = config
        self.repository = repository or AttentionRepository()
        self.clock = clock
        self.state = "disabled" if not config.enabled else "starting"
        self.state_error: str | None = None
        self._host_contract_error = host_contract_error
        self._host_contract_error_logged = False
        self._adapter: Any = None
        self._activation_id: str | None = None
        self._worker_task: asyncio.Task | None = None
        self._startup_task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None
        self._stopping = False
        self._native: Any = None
        self._native_listeners: list[tuple[Callable[..., Any], str]] = []
        self._task_factory: Callable[..., asyncio.Task] | None = None
        self._migration_ok = False
        try:
            self.repository.migrate()
            self._migration_ok = True
            if config.enabled and not config.valid:
                self.state = "config_error"
                self.state_error = "; ".join(config.errors)
            elif config.enabled and host_contract_error:
                self.state = "compatibility_error"
                self.state_error = host_contract_error
        except Exception as exc:
            self.state = "db_error" if config.enabled else "disabled"
            self.state_error = "database migration failed"
            logger.error("Thread attention database migration failed: %s", exc)

    @property
    def operational(self) -> bool:
        return self.state == "active"

    def _report_host_contract_error(self) -> bool:
        if not self._host_contract_error:
            return False
        self.state = "compatibility_error"
        self.state_error = self._host_contract_error
        if not self._host_contract_error_logged:
            logger.error("Thread attention compatibility error: %s", self.state_error)
            self._host_contract_error_logged = True
        return True

    @staticmethod
    def _is_discord_thread(event: object) -> bool:
        source = getattr(event, "source", None)
        return bool(
            _platform_name(getattr(source, "platform", None)) == "discord"
            and getattr(source, "chat_type", None) == "thread"
            and (
                getattr(source, "thread_id", None)
                or getattr(source, "chat_id", None)
            )
        )

    def _spawn(self, coro: Any, *, name: str | None = None) -> asyncio.Task | None:
        if self._task_factory is not None:
            try:
                return self._task_factory(coro, name=name)
            except Exception:
                logger.error("Could not spawn supervised plugin task", exc_info=True)
                if inspect.iscoroutine(coro):
                    coro.close()
                return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if inspect.iscoroutine(coro):
                coro.close()
            return None
        return loop.create_task(coro, name=name)

    async def _add_reaction(self, raw_message: object, emoji: str) -> None:
        callback = getattr(raw_message, "add_reaction", None)
        if callable(callback):
            try:
                result = callback(emoji)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.debug("Could not add thread-attention reaction", exc_info=True)

    async def _remove_processing_reaction(self, raw_message: object) -> None:
        callback = getattr(raw_message, "remove_reaction", None)
        if not callable(callback):
            return
        guild = getattr(raw_message, "guild", None)
        member = getattr(guild, "me", None)
        if member is None:
            return
        try:
            result = callback("⏳", member)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.debug("Could not remove processing reaction", exc_info=True)

    async def _finish_reaction(
        self,
        raw_message: object,
        processing_task: asyncio.Task | None,
        *,
        success: bool,
    ) -> None:
        if processing_task is not None:
            with suppress(Exception):
                await processing_task
        await self._remove_processing_reaction(raw_message)
        await self._add_reaction(raw_message, "✅" if success else "❌")

    def _wake_worker(self, adapter: Any = None) -> None:
        if adapter is not None:
            self._adapter = adapter
        if self._wake is not None:
            self._wake.set()
        if self._worker_task is None or self._worker_task.done():
            if self._adapter is not None and self.config.enabled:
                self._worker_task = self._spawn(
                    self._worker_loop(),
                    name="discord-related-threads:worker",
                )

    def on_discord_connected(
        self,
        *,
        native: Any,
        adapter: Any,
        spawn_task: Callable[..., asyncio.Task] | None = None,
    ) -> None:
        """Attach to Discord through documented stock plugin surfaces.

        ``register_platform_handler('discord', ...)`` calls this after the
        native bot is connected.  The adapter is retained only for documented
        public methods; native listeners observe live Hermes participation and
        delivery without dedicated core lifecycle/delivery hooks.
        """

        self._native = native
        self._adapter = adapter
        self._task_factory = spawn_task
        self._stopping = False
        if not self.config.enabled:
            return
        if self._report_host_contract_error():
            return
        self._wire_native_listeners()
        if self._startup_task is None or self._startup_task.done():
            self._startup_task = self._spawn(
                self._start_connected_runtime(),
                name="discord-related-threads:start",
            )

    def _wire_native_listeners(self) -> None:
        native = self._native
        add_listener = getattr(native, "add_listener", None)
        if not callable(add_listener) or self._native_listeners:
            return

        async def on_message(message: Any) -> None:
            self.on_native_discord_message(message)

        async def on_thread_create(thread: Any) -> None:
            self.on_native_discord_thread_create(thread)

        for callback, event_name in (
            (on_message, "on_message"),
            (on_thread_create, "on_thread_create"),
        ):
            add_listener(callback, event_name)
            self._native_listeners.append((callback, event_name))

    def _remove_native_listeners(self) -> None:
        native = self._native
        remove_listener = getattr(native, "remove_listener", None)
        if callable(remove_listener):
            for callback, event_name in self._native_listeners:
                try:
                    remove_listener(callback, event_name)
                except Exception:
                    logger.debug(
                        "Could not remove Discord plugin listener",
                        exc_info=True,
                    )
        self._native_listeners.clear()

    @staticmethod
    def _native_thread_fields(value: Any) -> dict[str, Any] | None:
        channel = getattr(value, "channel", None) or value
        parent_id = getattr(channel, "parent_id", None)
        thread_id = getattr(channel, "id", None)
        if not thread_id or not parent_id:
            return None
        guild = getattr(value, "guild", None) or getattr(channel, "guild", None)
        return {
            "thread_id": str(thread_id),
            "scope_id": str(getattr(guild, "id", "") or "") or None,
            "parent_channel_id": str(parent_id),
            "thread_name": str(getattr(channel, "name", "") or "") or None,
        }

    def on_native_discord_message(self, message: Any) -> None:
        """Observe successful bot-authored Discord messages via discord.py."""

        if not self.operational or self._native is None:
            return
        self_user = getattr(self._native, "user", None)
        author = getattr(message, "author", None)
        if (
            self_user is None
            or getattr(author, "id", None) != getattr(self_user, "id", None)
            or is_confirmation_template(getattr(message, "content", None))
        ):
            return
        fields = self._native_thread_fields(message)
        if fields is None:
            return
        try:
            self.repository.record_hermes_activity(
                thread_id=fields["thread_id"],
                message_id=str(getattr(message, "id", "") or "") or None,
                observed_at=getattr(message, "created_at", None) or self.clock(),
                scope_id=fields["scope_id"],
                parent_channel_id=fields["parent_channel_id"],
                thread_name=fields["thread_name"],
            )
            self._wake_worker()
        except Exception:
            logger.error("Could not record native Discord delivery", exc_info=True)

    def on_native_discord_thread_create(self, thread: Any) -> None:
        """Record a thread created by the connected Hermes bot."""

        if not self.operational or self._native is None:
            return
        self_user = getattr(self._native, "user", None)
        owner_id = getattr(thread, "owner_id", None)
        if self_user is None or owner_id != getattr(self_user, "id", None):
            return
        fields = self._native_thread_fields(thread)
        if fields is None:
            return
        try:
            self.repository.record_thread_participation(
                fields["thread_id"],
                observed_at=getattr(thread, "created_at", None) or self.clock(),
                scope_id=fields["scope_id"],
                parent_channel_id=fields["parent_channel_id"],
                thread_name=fields["thread_name"],
            )
            self._wake_worker()
        except Exception:
            logger.error("Could not record native Discord thread", exc_info=True)

    def on_pre_gateway_dispatch(self, **kwargs: Any) -> dict[str, str] | None:
        event = kwargs.get("event")
        if event is None or not self.config.enabled or not self._is_discord_thread(event):
            return None

        attempt = parse_command(getattr(event, "text", None))
        if attempt is not None and self.state == "compatibility_error":
            # Best-effort fail closed on an unsupported host.  The release
            # contract still requires pre-coalescing classification, but an
            # intact command that reaches this stock hook must never become an
            # agent turn merely because activation was refused.
            return {"action": "skip", "reason": "thread-attention-incompatible"}
        authorized = kwargs.get("is_authorized") is True
        fields = _source_fields(event)
        thread_id = fields["thread_id"]
        if not authorized:
            return None

        # Ordinary authorized prompts remain on the normal Hermes path, while
        # advancing the observable interaction/acknowledgement boundary.
        if attempt is None:
            if self.operational and thread_id:
                try:
                    self.repository.record_user_interaction(
                        thread_id=thread_id,
                        message_id=fields["message_id"],
                        observed_at=_event_time(event),
                        scope_id=fields["scope_id"],
                        parent_channel_id=fields["parent_channel_id"],
                        thread_name=fields["thread_name"],
                    )
                    self._wake_worker(kwargs.get("adapter"))
                except Exception:
                    logger.error(
                        "Could not record Discord thread interaction",
                        exc_info=True,
                    )
            return None

        raw_message = getattr(event, "raw_message", None)
        processing_task = (
            self._spawn(self._add_reaction(raw_message, "⏳"))
            if raw_message is not None
            else None
        )
        message_id = fields["message_id"]
        adapter = kwargs.get("adapter")
        if adapter is not None:
            self._adapter = adapter

        if not message_id or not thread_id:
            if raw_message is not None:
                self._spawn(
                    self._finish_reaction(raw_message, processing_task, success=False)
                )
            self._spawn(
                self._send_unledgered_failure(
                    adapter,
                    thread_id or "",
                    message_id,
                    outcome_code="db_error",
                )
            )
            return {"action": "skip", "reason": "thread-attention-missing-id"}

        forced_outcome: str | None = None
        if not self._migration_ok or self.state == "db_error":
            forced_outcome = "db_error"
        elif not self.config.valid or self.state == "config_error":
            forced_outcome = "config_error"
        elif not self.operational:
            forced_outcome = "starting"

        due_date = None
        if attempt.valid and attempt.action is CommandAction.REMIND and attempt.days:
            local_event_date = _event_time(event).astimezone(self.config.timezone).date()
            from datetime import timedelta

            due_date = local_event_date + timedelta(days=attempt.days)

        try:
            result = self.repository.process_command(
                attempt=attempt,
                source_message_id=message_id,
                thread_id=thread_id,
                scope_id=fields["scope_id"],
                target_channel_id=thread_id,
                observed_at=_event_time(event),
                due_local_date=due_date,
                forced_outcome=forced_outcome,
            )
            success = result.outcome_code in {
                "seen",
                "reminder_set",
                "reminder_cancelled",
                "reminder_already_clear",
                "closed",
            }
            if raw_message is not None:
                self._spawn(
                    self._finish_reaction(raw_message, processing_task, success=success)
                )
            self._wake_worker(adapter)
        except Exception:
            logger.error("Thread-attention command transaction failed", exc_info=True)
            if raw_message is not None:
                self._spawn(
                    self._finish_reaction(raw_message, processing_task, success=False)
                )
            self._spawn(
                self._send_unledgered_failure(
                    adapter,
                    thread_id,
                    message_id,
                    outcome_code="db_error",
                )
            )
        return {"action": "skip", "reason": "thread-attention-command"}

    async def _send_unledgered_failure(
        self,
        adapter: Any,
        thread_id: str,
        message_id: str | None,
        *,
        outcome_code: str,
    ) -> None:
        if adapter is None or not thread_id:
            return
        content = render_confirmation(outcome_code=outcome_code, command="")
        try:
            await adapter.send(
                thread_id,
                content,
                reply_to=message_id,
                metadata={
                    "thread_id": thread_id,
                    "non_conversational": True,
                    "non_conversational_history": True,
                },
            )
        except Exception:
            logger.error("Could not deliver unledgered command failure", exc_info=True)

    def on_history_message(self, **kwargs: Any) -> bool:
        """Return True for a ledger ID or deterministic crash-window fallback."""

        if _platform_name(kwargs.get("platform")) != "discord":
            return False
        message_id = str(kwargs.get("message_id") or "")
        if message_id and self._migration_ok:
            if self.repository.has_history_exclusion(message_id):
                return True
        if kwargs.get("author_is_self") is True and is_confirmation_template(
            kwargs.get("content")
        ):
            return True
        if not self.config.enabled:
            return False
        if (
            kwargs.get("chat_type") == "thread"
            and kwargs.get("author_is_authorized") is True
            and parse_command(kwargs.get("content")) is not None
        ):
            return True
        return False

    def on_control_message(self, **kwargs: Any) -> bool:
        """Claim recognized commands before any gateway text coalescing."""

        event = kwargs.get("event")
        return bool(
            self.config.enabled
            and _platform_name(kwargs.get("platform")) == "discord"
            and event is not None
            and self._is_discord_thread(event)
            and parse_command(getattr(event, "text", None)) is not None
        )

    async def _start_connected_runtime(self) -> None:
        if not self.config.enabled:
            return
        if self._report_host_contract_error():
            return
        if not self._migration_ok:
            self.state = "db_error"
            return
        self.repository.recover_attempting(observed_at=self.clock())
        await self._activate_if_possible()
        self._start_worker()

    async def _activate_if_possible(self) -> bool:
        if self._report_host_contract_error():
            return False
        if not self.config.valid:
            self.state = "config_error"
            self.state_error = "; ".join(self.config.errors)
            logger.error("Thread attention configuration error: %s", self.state_error)
            return False
        if self._adapter is None:
            self.state = "starting"
            self.state_error = "Discord adapter is not connected"
            logger.warning("Thread attention waiting for a Discord adapter")
            return False
        required_methods = (
            "validate_delivery_target",
            "participating_thread_ids",
            "resolve_thread_metadata",
            "send",
        )
        missing = [
            name
            for name in required_methods
            if not callable(getattr(self._adapter, name, None))
        ]
        if missing:
            self.state = "compatibility_error"
            self.state_error = (
                "unsupported Hermes Discord plugin contract; missing: "
                + ", ".join(missing)
            )
            logger.error("Thread attention compatibility error: %s", self.state_error)
            return False
        validator = getattr(self._adapter, "validate_delivery_target")
        try:
            validation = validator(self.config.digest_channel_id)
            if inspect.isawaitable(validation):
                validation = await validation
        except Exception as exc:
            validation = {"ok": False, "error": type(exc).__name__}
        valid_target = (
            validation is True
            or (isinstance(validation, Mapping) and validation.get("ok") is True)
        )
        if not valid_target:
            self.state = "config_error"
            self.state_error = (
                str(validation.get("error") or "delivery target unavailable")
                if isinstance(validation, Mapping)
                else "delivery target unavailable"
            )
            logger.error("Thread attention configuration error: %s", self.state_error)
            return False
        self.state = "active"
        self.state_error = None
        ids_getter = getattr(self._adapter, "participating_thread_ids", None)
        try:
            thread_ids = ids_getter() if callable(ids_getter) else ()
        except Exception:
            logger.warning("Could not snapshot Discord participation IDs", exc_info=True)
            thread_ids = ()
        self._activation_id = self.repository.ensure_activation(
            thread_ids or (), observed_at=self.clock()
        )
        self.repository.reconcile_participation_ids(
            thread_ids or (), observed_at=self.clock()
        )
        return True

    def _start_worker(self) -> None:
        self._stopping = False
        if self._wake is None:
            self._wake = asyncio.Event()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = self._spawn(
                self._worker_loop(),
                name="discord-related-threads:worker",
            )
        self._wake.set()

    async def shutdown(self) -> None:
        """Cancel and await runtime-owned tasks for deterministic shutdown."""

        self._stop_background_tasks()
        task = self._worker_task
        startup = self._startup_task
        self._worker_task = None
        self._startup_task = None
        for pending in (startup, task):
            if pending is not None and not pending.done():
                with suppress(asyncio.CancelledError):
                    await pending

    def _stop_background_tasks(self) -> None:
        self._stopping = True
        for task in (self._startup_task, self._worker_task):
            if task is not None and not task.done():
                task.cancel()

    def on_unload(self) -> None:
        """Release native listeners and background work on plugin unload."""

        self._stop_background_tasks()
        self._remove_native_listeners()
        self._native = None
        self._adapter = None
        self._task_factory = None

    async def _resolve_adapter_if_needed(self) -> None:
        if self._adapter is not None and self.state == "starting":
            await self._activate_if_possible()

    async def _process_backfill_batch(self) -> bool:
        if not self.operational or not self._activation_id or self._adapter is None:
            return False
        if self.repository.activation_status(self._activation_id) == "ready":
            return False
        resolver = getattr(self._adapter, "resolve_thread_metadata", None)
        if not callable(resolver):
            logger.error("Discord adapter lacks thread metadata resolution")
            return False
        ids = self.repository.pending_backfill(self._activation_id, limit=20)
        today = self.clock().astimezone(self.config.timezone).date()
        if not ids:
            completed = self.repository.complete_activation_if_ready(
                activation_id=self._activation_id,
                digest_channel_id=str(self.config.digest_channel_id),
                observed_at=self.clock(),
            )
            return completed
        for thread_id in ids:
            try:
                metadata = resolver(thread_id)
                if inspect.isawaitable(metadata):
                    metadata = await metadata
                if not isinstance(metadata, Mapping):
                    metadata = {"accessible": False}
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Could not resolve Discord thread metadata for %s",
                    thread_id,
                    exc_info=True,
                )
                metadata = {"accessible": False}
            self.repository.record_backfill_result(
                activation_id=self._activation_id,
                thread_id=thread_id,
                metadata=metadata,
                local_date=today,
                observed_at=self.clock(),
            )
        self.repository.complete_activation_if_ready(
            activation_id=self._activation_id,
            digest_channel_id=str(self.config.digest_channel_id),
            observed_at=self.clock(),
        )
        return True

    async def _refresh_metadata_batch(self) -> bool:
        if not self.operational or self._adapter is None:
            return False
        resolver = getattr(self._adapter, "resolve_thread_metadata", None)
        if not callable(resolver):
            return False
        today = self.clock().astimezone(self.config.timezone).date()
        local_midnight_utc = datetime.combine(
            today,
            datetime.min.time(),
            tzinfo=self.config.timezone,
        ).astimezone(UTC)
        thread_ids = self.repository.metadata_refresh_thread_ids(
            local_date=today,
            accessible_checked_before=local_midnight_utc,
            limit=20,
        )
        if not thread_ids:
            return False
        for thread_id in thread_ids:
            try:
                metadata = resolver(thread_id, include_activity_history=False)
                if inspect.isawaitable(metadata):
                    metadata = await metadata
                if not isinstance(metadata, Mapping):
                    metadata = {"accessible": False}
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Could not refresh Discord thread metadata for %s",
                    thread_id,
                    exc_info=True,
                )
                metadata = {"accessible": False}
            self.repository.record_metadata_result(
                thread_id=thread_id,
                metadata=metadata,
                local_date=today,
                observed_at=self.clock(),
            )
        return True

    def _ensure_today_digest(self) -> None:
        if not self.operational or not self._activation_id:
            return
        if self.repository.activation_status(self._activation_id) != "ready":
            return
        local_now = self.clock().astimezone(self.config.timezone)
        if local_now.time().replace(tzinfo=None) < self.config.digest_time:
            return
        self.repository.ensure_digest_outbox(
            local_date=local_now.date(),
            digest_channel_id=str(self.config.digest_channel_id),
            observed_at=self.clock(),
        )

    async def _worker_loop(self) -> None:
        if self._wake is None:
            self._wake = asyncio.Event()
        while not self._stopping:
            try:
                # Clear before inspecting durable work so a wake arriving
                # during the iteration remains set for the wait below.
                self._wake.clear()
                await self._resolve_adapter_if_needed()
                progressed = await self._process_backfill_batch()
                # Linkable rows are refreshed daily in bounded batches.  Do
                # not turn metadata maintenance into a tight REST loop; absent
                # other work, the normal 30-second cadence spaces batches out.
                await self._refresh_metadata_batch()
                self._ensure_today_digest()
                allowed = None if self.operational else ("command_confirmation",)
                if self._adapter is not None:
                    item = self.repository.claim_due_outbox(
                        observed_at=self.clock(), allowed_kinds=allowed
                    )
                    if item is not None:
                        await self._deliver(item)
                        progressed = True
                if progressed:
                    await asyncio.sleep(0)
                    continue
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Thread-attention worker iteration failed", exc_info=True)
                await asyncio.sleep(1)

    @staticmethod
    def _message_ids(result: object) -> tuple[str, ...]:
        values: list[str] = []
        primary = getattr(result, "message_id", None)
        if primary:
            values.append(str(primary))
        for value in getattr(result, "continuation_message_ids", ()) or ():
            if value:
                values.append(str(value))
        raw = getattr(result, "raw_response", None)
        if isinstance(raw, Mapping):
            for value in raw.get("message_ids", ()) or ():
                if value:
                    values.append(str(value))
        return tuple(dict.fromkeys(values))

    def _render_outbox(
        self, item: OutboxItem
    ) -> tuple[str, tuple[str, ...]]:
        if item.kind == "command_confirmation":
            payload = item.payload
            return (
                render_confirmation(
                    outcome_code=str(payload.get("outcome_code") or "db_error"),
                    command=str(payload.get("command") or ""),
                    days=payload.get("days"),
                    due_date=payload.get("due_local_date"),
                    digest_time_label=self.config.digest_time_label,
                    safe_bad_arg=payload.get("safe_bad_arg"),
                    retry_attempt=item.attempts,
                ),
                (),
            )
        if item.kind == "initial_summary":
            prefix = (
                f"↻ 초기 가져오기 · 재시도 {item.attempts}\n"
                if item.attempts > 1
                else ""
            )
            return (
                prefix
                + "초기 가져오기: 총 {total}개 등록 · 링크 가능 {accessible}개 · "
                "접근 불가 {inaccessible}개".format(**item.payload),
                (),
            )
        if item.kind == "digest":
            now = self.clock()
            selection = select_digest(
                self.repository.inventory_rows(),
                now=now,
                digest_time=self.config.digest_time,
                timezone_info=self.config.timezone,
            )
            return (
                render_digest(
                    selection,
                    now=now,
                    timezone_info=self.config.timezone,
                    retry_attempt=item.attempts,
                ),
                tuple(candidate.thread_id for candidate in selection.items),
            )
        if item.kind == "source_warning":
            payload = item.payload
            thread_id = str(payload.get("thread_id") or "")
            scope_id = str(payload.get("scope_id") or "")
            if scope_id:
                link = f"https://discord.com/channels/{scope_id}/{thread_id}"
            else:
                link = f"https://discord.com/channels/@me/{thread_id}"
            applied = "성공" if payload.get("applied") is True else "미적용"
            return (
                f"⚠️ 명령 확인 전달 중단 · 장부 적용 {applied} · {link}",
                (),
            )
        if item.kind == "channel_recovery":
            def local_label(value: object) -> str:
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    return parsed.astimezone(self.config.timezone).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                except (TypeError, ValueError):
                    return "시각 불명"

            return (
                "⚠️ Hermes 검토 채널 전달 복구 · 중단 "
                f"{local_label(item.payload.get('started_at'))} · 복구 "
                f"{local_label(item.payload.get('recovered_at'))}",
                (),
            )
        raise ValueError(f"unknown outbox kind: {item.kind}")

    async def _deliver(self, item: OutboxItem) -> None:
        content, exposed = self._render_outbox(item)
        metadata: dict[str, Any] = {
            "non_conversational": True,
            "non_conversational_history": True,
        }
        if item.kind == "command_confirmation" and item.source_thread_id:
            metadata["thread_id"] = item.source_thread_id
        is_digest_target = bool(
            self.config.digest_channel_id
            and str(item.target_channel_id) == str(self.config.digest_channel_id)
        )
        try:
            result = await self._adapter.send(
                item.target_channel_id,
                content,
                reply_to=item.source_message_id,
                metadata=metadata,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outage_started = self.repository.mark_outbox_failed(
                item.id,
                attempts=item.attempts,
                error_code=type(exc).__name__,
                observed_at=self.clock(),
                record_digest_outage=is_digest_target,
            )
            if outage_started:
                logger.error(
                    "Thread-attention digest channel delivery unavailable: %s",
                    type(exc).__name__,
                )
            return
        if getattr(result, "success", False):
            self.repository.mark_outbox_delivered(
                item.id,
                message_ids=self._message_ids(result),
                exposed_thread_ids=exposed,
                observed_at=self.clock(),
                digest_channel_id=(
                    str(self.config.digest_channel_id)
                    if is_digest_target
                    else None
                ),
            )
            return
        error_kind = str(getattr(result, "error_kind", None) or "unknown")
        permanent_source_failure = (
            item.kind == "command_confirmation"
            and error_kind in {"forbidden", "not_found"}
        )
        if permanent_source_failure and self.config.digest_channel_id:
            self.repository.abandon_source_confirmation_and_warn(
                item.id,
                error_code=error_kind,
                digest_channel_id=str(self.config.digest_channel_id),
                observed_at=self.clock(),
            )
            return
        outage_started = self.repository.mark_outbox_failed(
            item.id,
            attempts=item.attempts,
            error_code=error_kind,
            observed_at=self.clock(),
            abandoned=permanent_source_failure,
            record_digest_outage=is_digest_target,
        )
        if permanent_source_failure:
            logger.error(
                "Thread-attention source confirmation permanently unavailable; "
                "no digest channel is configured"
            )
        if outage_started:
            logger.error(
                "Thread-attention digest channel delivery unavailable: %s",
                error_kind,
            )
