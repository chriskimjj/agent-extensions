"""Deterministic one-letter command grammar and confirmation templates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum


COMMAND_LIST = (
    "명령: !s/!ㄴ 확인 · !r 30d/!ㄱ 30ㅇ 재알림 · "
    "!r -/!ㄱ - 취소 · !c/!ㅊ 종료"
)

_COMMANDS = {
    "!s": "s",
    "!ㄴ": "s",
    "!r": "r",
    "!ㄱ": "r",
    "!c": "c",
    "!ㅊ": "c",
}
_REMINDER_RE = re.compile(r"^([0-9]+)([dDㅇ])$")
_SAFE_BAD_ARG_RE = re.compile(r"^[0-9A-Za-zㄱ-ㅎㅏ-ㅣ가-힣-]{1,16}$")
_CONFIRMATION_FIRST_PATTERNS = (
    re.compile(r"^✅ 확인으로 기록됨$"),
    re.compile(
        r"^✅ !(?:r|ㄱ) [0-9]+[dㅇ] → [0-9]+일 뒤\([0-9]{4}-[0-9]{2}-[0-9]{2} "
        r"[0-9]{2}:[0-9]{2}\) 다이제스트로 예약됨$"
    ),
    re.compile(r"^✅ 재알림 취소됨$"),
    re.compile(r"^✅ 활성 재알림 없음\(변경 없음\)$"),
    re.compile(r"^✅ 종료됨$"),
    re.compile(r"^❌ 다이제스트 채널 설정 오류: 채널 ID 또는 봇 권한을 확인해 주세요$"),
    re.compile(r"^❌ 쓰레드 검토 기능 초기화 중: 잠시 뒤 다시 시도해 주세요$"),
    re.compile(r"^❌ 장부 저장 실패: 상태를 변경하지 못했습니다$"),
    re.compile(r"^❌ 재알림 일수는 1~3650 사이여야 함$"),
    re.compile(r"^❌ `[0-9A-Za-zㄱ-ㅎㅏ-ㅣ가-힣-]{1,16}`은 인식할 수 없음$"),
    re.compile(r"^❌ 명령 형식 오류: 아래 형식을 사용해 주세요$"),
)


class CommandAction(str, Enum):
    SEEN = "seen"
    REMIND = "remind"
    CANCEL_REMINDER = "cancel_reminder"
    CLOSE = "close"


@dataclass(frozen=True)
class CommandAttempt:
    recognized: bool
    valid: bool
    command: str
    action: CommandAction | None = None
    days: int | None = None
    error_code: str | None = None
    safe_bad_arg: str | None = None


def parse_command(text: object) -> CommandAttempt | None:
    """Return a recognized attempt, or ``None`` for an unrelated message."""

    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None

    parts = stripped.split()
    first = parts[0]
    canonical = _COMMANDS.get(first.lower())
    if canonical is None:
        return None

    display_command = first.lower() if first[:1] == "!" else first
    if canonical == "s":
        if len(parts) == 1:
            return CommandAttempt(True, True, display_command, CommandAction.SEEN)
        return CommandAttempt(True, False, display_command, error_code="unexpected_argument")

    if canonical == "c":
        if len(parts) == 1:
            return CommandAttempt(True, True, display_command, CommandAction.CLOSE)
        return CommandAttempt(True, False, display_command, error_code="unexpected_argument")

    if len(parts) != 2:
        return CommandAttempt(True, False, display_command, error_code="reminder_syntax")
    raw_arg = parts[1]
    if raw_arg == "-":
        return CommandAttempt(
            True,
            True,
            display_command,
            CommandAction.CANCEL_REMINDER,
        )

    match = _REMINDER_RE.fullmatch(raw_arg)
    if match is None:
        safe_arg = raw_arg if _SAFE_BAD_ARG_RE.fullmatch(raw_arg) else None
        return CommandAttempt(
            True,
            False,
            display_command,
            error_code="reminder_syntax",
            safe_bad_arg=safe_arg,
        )
    days = int(match.group(1))
    if not 1 <= days <= 3650:
        return CommandAttempt(
            True,
            False,
            display_command,
            error_code="reminder_range",
            safe_bad_arg=raw_arg if len(raw_arg) <= 16 else None,
        )
    return CommandAttempt(
        True,
        True,
        display_command,
        CommandAction.REMIND,
        days=days,
    )


def render_confirmation(
    *,
    outcome_code: str,
    command: str,
    days: int | None = None,
    due_date: date | str | None = None,
    digest_time_label: str = "09:00",
    safe_bad_arg: str | None = None,
    retry_attempt: int = 1,
) -> str:
    """Render one confirmation solely from validated, minimal ledger fields."""

    if isinstance(due_date, date):
        due_label = due_date.isoformat()
    else:
        due_label = str(due_date or "")

    if outcome_code == "seen":
        first = "✅ 확인으로 기록됨"
    elif outcome_code == "reminder_set":
        unit = "ㅇ" if command == "!ㄱ" else "d"
        first = (
            f"✅ {command} {days}{unit} → {days}일 뒤"
            f"({due_label} {digest_time_label}) 다이제스트로 예약됨"
        )
    elif outcome_code == "reminder_cancelled":
        first = "✅ 재알림 취소됨"
    elif outcome_code == "reminder_already_clear":
        first = "✅ 활성 재알림 없음(변경 없음)"
    elif outcome_code == "closed":
        first = "✅ 종료됨"
    elif outcome_code == "config_error":
        first = "❌ 다이제스트 채널 설정 오류: 채널 ID 또는 봇 권한을 확인해 주세요"
    elif outcome_code == "starting":
        first = "❌ 쓰레드 검토 기능 초기화 중: 잠시 뒤 다시 시도해 주세요"
    elif outcome_code == "db_error":
        first = "❌ 장부 저장 실패: 상태를 변경하지 못했습니다"
    elif outcome_code == "reminder_range":
        first = "❌ 재알림 일수는 1~3650 사이여야 함"
    elif safe_bad_arg:
        first = f"❌ `{safe_bad_arg}`은 인식할 수 없음"
    else:
        first = "❌ 명령 형식 오류: 아래 형식을 사용해 주세요"

    if retry_attempt > 1:
        first = f"↻ 지연 확인 · {first}"
    return f"{first}\n{COMMAND_LIST}"


def is_confirmation_template(content: object) -> bool:
    """Recognize only this plugin's exact two-line bot confirmation shape."""

    if not isinstance(content, str):
        return False
    lines = content.strip().splitlines()
    if len(lines) != 2 or lines[1] != COMMAND_LIST:
        return False
    first = lines[0]
    if first.startswith("↻ 지연 확인 · "):
        first = first.removeprefix("↻ 지연 확인 · ")
    return any(pattern.fullmatch(first) for pattern in _CONFIRMATION_FIRST_PATTERNS)
