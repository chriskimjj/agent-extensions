"""Pure candidate selection and metadata-only digest rendering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo


UTC = timezone.utc
MAX_ITEMS = 10


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _local_digest_datetime(
    local_date: date,
    digest_time: time,
    timezone_info: ZoneInfo,
) -> datetime:
    return datetime.combine(local_date, digest_time, tzinfo=timezone_info).astimezone(UTC)


@dataclass(frozen=True)
class DigestCandidate:
    thread_id: str
    scope_id: str
    thread_name: str
    reasons: tuple[str, ...]
    activity_at: datetime
    automatic_due_at: datetime | None
    reminder_due_at: datetime | None
    archive_at: datetime | None
    last_exposed_at: datetime | None
    historical: bool

    @property
    def has_reminder(self) -> bool:
        return self.reminder_due_at is not None

    @property
    def effective_due_at(self) -> datetime:
        values = [v for v in (self.automatic_due_at, self.reminder_due_at) if v]
        return min(values) if values else self.activity_at


@dataclass(frozen=True)
class DigestSelection:
    local_date: date
    items: tuple[DigestCandidate, ...]
    total_candidates: int

    @property
    def outside_count(self) -> int:
        return max(0, self.total_candidates - len(self.items))


def _candidate_from_row(
    row: Mapping[str, Any],
    *,
    now: datetime,
    digest_time: time,
    timezone_info: ZoneInfo,
) -> DigestCandidate | None:
    if row.get("closed_at") or row.get("link_state") != "accessible":
        return None
    activity_at = _parse_datetime(row.get("last_hermes_activity_at"))
    if activity_at is None:
        return None

    now_utc = now.astimezone(UTC)
    acknowledged_at = _parse_datetime(row.get("acknowledged_at"))
    last_user = _parse_datetime(row.get("last_user_interaction_at"))
    last_exposed = _parse_datetime(row.get("last_exposed_at"))
    archive_at = _parse_datetime(row.get("archive_at"))
    historical = bool(row.get("historical"))

    base_due_date = activity_at.astimezone(timezone_info).date() + timedelta(days=3)
    base_due_at = _local_digest_datetime(base_due_date, digest_time, timezone_info)
    auto_open = acknowledged_at is None or activity_at > acknowledged_at

    archive_due_at = archive_at - timedelta(hours=24) if archive_at else None
    automatic_due_at: datetime | None = None
    archive_reason = False
    if auto_open:
        automatic_due_at = base_due_at
        if archive_due_at is not None and archive_due_at < base_due_at:
            automatic_due_at = archive_due_at
            archive_reason = now_utc >= archive_due_at
        if now_utc < automatic_due_at:
            automatic_due_at = None

    reminder_due_at: datetime | None = None
    reminder_set_at = _parse_datetime(row.get("reminder_set_at"))
    if bool(row.get("reminder_active")) and row.get("reminder_due_local_date"):
        try:
            reminder_date = date.fromisoformat(str(row["reminder_due_local_date"]))
            candidate_due = _local_digest_datetime(
                reminder_date, digest_time, timezone_info
            )
            if now_utc >= candidate_due:
                reminder_due_at = candidate_due
        except ValueError:
            reminder_due_at = None

    if automatic_due_at is None and reminder_due_at is None:
        return None

    if last_exposed is not None:
        next_regular_date = (
            last_exposed.astimezone(timezone_info).date() + timedelta(days=3)
        )
        cooldown_at = _local_digest_datetime(
            next_regular_date, digest_time, timezone_info
        )
        reminder_overrides = bool(
            reminder_due_at
            and reminder_set_at
            and reminder_set_at > last_exposed
            and reminder_due_at < cooldown_at
        )
        if now_utc < cooldown_at:
            automatic_due_at = None
            if not reminder_overrides:
                reminder_due_at = None
        if automatic_due_at is None and reminder_due_at is None:
            return None

    reasons: list[str] = []
    if automatic_due_at is not None:
        if historical and last_user is None:
            reasons.append("과거")
        elif acknowledged_at is not None and activity_at > acknowledged_at:
            reasons.append("새 활동")
        else:
            reasons.append("미확인")
        if archive_reason:
            reasons.append("보관 임박")
    if reminder_due_at is not None:
        reasons.append("재알림")

    return DigestCandidate(
        thread_id=str(row["thread_id"]),
        scope_id=str(row.get("scope_id") or ""),
        thread_name=str(row.get("thread_name") or f"쓰레드 {row['thread_id']}"),
        reasons=tuple(reasons),
        activity_at=activity_at,
        automatic_due_at=automatic_due_at,
        reminder_due_at=reminder_due_at,
        archive_at=archive_at,
        last_exposed_at=last_exposed,
        historical=historical,
    )


def _common_sort_key(candidate: DigestCandidate) -> tuple[Any, ...]:
    return (
        candidate.last_exposed_at is not None,
        candidate.last_exposed_at or datetime.min.replace(tzinfo=UTC),
        candidate.effective_due_at,
        candidate.thread_id,
    )


def _automatic_sort_key(candidate: DigestCandidate) -> tuple[Any, ...]:
    if candidate.last_exposed_at is None and candidate.historical:
        # Unexposed historical candidates rotate from recent to old.
        return (
            0,
            -candidate.activity_at.timestamp(),
            candidate.effective_due_at.timestamp(),
            candidate.thread_id,
        )
    return (
        0 if candidate.last_exposed_at is None else 1,
        (candidate.last_exposed_at or datetime.min.replace(tzinfo=UTC)).timestamp(),
        candidate.effective_due_at.timestamp(),
        candidate.thread_id,
    )


def _choose_automatic(
    automatic: Sequence[DigestCandidate],
    limit: int,
) -> list[DigestCandidate]:
    if limit <= 0:
        return []
    new = sorted((item for item in automatic if not item.historical), key=_automatic_sort_key)
    historical = sorted(
        (item for item in automatic if item.historical), key=_automatic_sort_key
    )
    chosen: list[DigestCandidate] = []

    new_quota = min(3, limit)
    historical_quota = min(2, max(0, limit - new_quota))
    chosen.extend(new[:new_quota])
    chosen.extend(historical[:historical_quota])

    remaining_slots = limit - len(chosen)
    if remaining_slots > 0:
        used = {item.thread_id for item in chosen}
        leftovers = sorted(
            (item for item in automatic if item.thread_id not in used),
            key=_automatic_sort_key,
        )
        chosen.extend(leftovers[:remaining_slots])
    return chosen


def select_digest(
    rows: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
    digest_time: time,
    timezone_info: ZoneInfo,
) -> DigestSelection:
    """Apply overlap de-duplication and the agreed 5+5 / 3+2 allocation."""

    candidates = [
        candidate
        for row in rows
        if (
            candidate := _candidate_from_row(
                row,
                now=now,
                digest_time=digest_time,
                timezone_info=timezone_info,
            )
        )
        is not None
    ]
    reminder = sorted(
        (item for item in candidates if item.has_reminder), key=_common_sort_key
    )
    automatic = [item for item in candidates if not item.has_reminder]

    chosen_reminder = reminder[:5]
    chosen_auto = _choose_automatic(automatic, 5)
    chosen = chosen_reminder + chosen_auto

    if len(chosen) < MAX_ITEMS:
        used = {item.thread_id for item in chosen}
        leftovers = sorted(
            (item for item in candidates if item.thread_id not in used),
            key=_common_sort_key,
        )
        chosen.extend(leftovers[: MAX_ITEMS - len(chosen)])

    chosen.sort(key=_common_sort_key)
    return DigestSelection(
        local_date=now.astimezone(timezone_info).date(),
        items=tuple(chosen[:MAX_ITEMS]),
        total_candidates=len(candidates),
    )


def _safe_name(value: str, *, limit: int = 48) -> str:
    cleaned = " ".join(value.replace("[", "(").replace("]", ")").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"


def _activity_label(
    activity_at: datetime,
    now: datetime,
    timezone_info: ZoneInfo,
) -> str:
    elapsed = max(timedelta(0), now.astimezone(UTC) - activity_at)
    if elapsed < timedelta(days=1):
        return f"Hermes 활동 {int(elapsed.total_seconds() // 3600)}시간 전"
    days = (
        now.astimezone(timezone_info).date()
        - activity_at.astimezone(timezone_info).date()
    ).days
    return f"Hermes 활동 {max(1, days)}일 전"


def render_digest(
    selection: DigestSelection,
    *,
    now: datetime,
    timezone_info: ZoneInfo,
    retry_attempt: int = 1,
) -> str:
    title = f"Hermes 검토 · {selection.local_date.isoformat()}"
    if retry_attempt > 1:
        title += f" · 재시도 {retry_attempt}"
    if not selection.items:
        return f"{title}\n오늘 다시 볼 쓰레드는 0개입니다."

    summary = f"표시 {len(selection.items)}개"
    if selection.outside_count:
        summary += f" · 외 {selection.outside_count}개"
    lines = [title, summary, ""]
    for index, item in enumerate(selection.items, start=1):
        name = _safe_name(item.thread_name)
        if item.scope_id:
            link = f"https://discord.com/channels/{item.scope_id}/{item.thread_id}"
        else:
            link = f"https://discord.com/channels/@me/{item.thread_id}"
        timing: list[str] = []
        if any(reason in item.reasons for reason in ("미확인", "새 활동", "과거")):
            timing.append(_activity_label(item.activity_at, now, timezone_info))
        if "보관 임박" in item.reasons:
            if item.archive_at is None or item.archive_at <= now.astimezone(UTC):
                timing.append("보관됨")
            else:
                hours = max(
                    1,
                    int((item.archive_at - now.astimezone(UTC)).total_seconds() // 3600),
                )
                timing.append(f"보관까지 약 {hours}시간")
        if "재알림" in item.reasons and item.reminder_due_at is not None:
            due_local = item.reminder_due_at.astimezone(timezone_info)
            if due_local.date() == selection.local_date:
                timing.append(f"예약 오늘 {due_local:%H:%M}")
            else:
                timing.append(f"예약 {due_local:%m-%d %H:%M}")
        details = " · ".join(["+".join(item.reasons), *timing])
        lines.append(f"{index}. [{name}]({link}) — {details}")
    return "\n".join(lines)
