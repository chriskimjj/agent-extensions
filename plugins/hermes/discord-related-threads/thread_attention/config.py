"""Strict, side-effect-free configuration parsing for thread attention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_DIGEST_TIME = "09:00"
DEFAULT_TIMEZONE = "Asia/Seoul"


@dataclass(frozen=True)
class ThreadAttentionConfig:
    """Validated profile-local feature settings.

    ``enabled`` is true only for an explicit YAML boolean ``true``.  Invalid
    enabled configurations retain their validation errors so the runtime can
    fail closed for recognized commands without starting collectors.
    """

    enabled: bool = False
    digest_channel_id: str | None = None
    digest_time: time = time(9, 0)
    timezone_name: str = DEFAULT_TIMEZONE
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def digest_time_label(self) -> str:
        return self.digest_time.strftime("%H:%M")


def _feature_mapping(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(config, Mapping):
        return {}
    plugins = config.get("plugins")
    if not isinstance(plugins, Mapping):
        return {}
    entries = plugins.get("entries")
    if not isinstance(entries, Mapping):
        return {}
    entry = entries.get("discord-related-threads")
    if not isinstance(entry, Mapping):
        return {}
    feature = entry.get("thread_attention")
    return feature if isinstance(feature, Mapping) else {}


def parse_thread_attention_config(
    config: Mapping[str, Any] | None,
) -> ThreadAttentionConfig:
    raw = _feature_mapping(config)
    enabled_raw = raw.get("enabled", False)
    errors: list[str] = []

    if not isinstance(enabled_raw, bool):
        errors.append("thread_attention.enabled must be a boolean")
        enabled = False
    else:
        enabled = enabled_raw

    digest_channel_id: str | None = None
    channel_raw = raw.get("digest_channel_id")
    if isinstance(channel_raw, str) and channel_raw.isdigit() and int(channel_raw) > 0:
        digest_channel_id = channel_raw
    elif enabled:
        errors.append(
            "thread_attention.digest_channel_id must be a positive Discord snowflake string"
        )

    digest_raw = raw.get("digest_time", DEFAULT_DIGEST_TIME)
    digest_value = time(9, 0)
    if isinstance(digest_raw, str):
        try:
            hour_text, minute_text = digest_raw.split(":", 1)
            if (
                len(hour_text) != 2
                or len(minute_text) != 2
                or not hour_text.isdigit()
                or not minute_text.isdigit()
            ):
                raise ValueError
            digest_value = time(int(hour_text), int(minute_text))
        except (TypeError, ValueError):
            if enabled:
                errors.append("thread_attention.digest_time must use 24-hour HH:MM")
    elif enabled:
        errors.append("thread_attention.digest_time must use 24-hour HH:MM")

    timezone_raw = raw.get("timezone", DEFAULT_TIMEZONE)
    timezone_name = timezone_raw if isinstance(timezone_raw, str) else DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        if enabled:
            errors.append("thread_attention.timezone must be an IANA timezone name")
        timezone_name = DEFAULT_TIMEZONE

    return ThreadAttentionConfig(
        enabled=enabled,
        digest_channel_id=digest_channel_id,
        digest_time=digest_value,
        timezone_name=timezone_name,
        errors=tuple(errors),
    )


def load_thread_attention_config() -> ThreadAttentionConfig:
    """Load the active Hermes profile config without making it a test dependency."""

    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except (ImportError, AttributeError):
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except ImportError:
            config = {}
    return parse_thread_attention_config(config)
