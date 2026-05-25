"""Codex limit-utilization reporting from rollout token events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from llm_report.report import _render_table


@dataclass
class DayBuckets:
    active: set[int] = field(default_factory=set)
    near_5h: set[int] = field(default_factory=set)
    near_weekly: set[int] = field(default_factory=set)
    constrained_5h: set[int] = field(default_factory=set)
    constrained_weekly: set[int] = field(default_factory=set)


@dataclass
class MonthSummary:
    days: int = 0
    active_slots: int = 0
    productive_slots: int = 0
    overhead_slots: int = 0
    constrained_5h_slots: int = 0
    constrained_weekly_slots: int = 0
    near_5h_days: int = 0
    near_weekly_days: int = 0


@dataclass
class UtilizationReport:
    generated_at: str
    homes: list[str]
    timezone: str
    slot_minutes: int
    threshold_percent: float
    productive_day_hours: float
    home_accounts: dict[str, str]
    monthly_by_home: dict[str, dict[str, MonthSummary]]
    monthly_by_account: dict[str, dict[str, MonthSummary]]


@dataclass(frozen=True)
class _TokenEvent:
    timestamp: datetime
    primary_percent: float | None
    primary_reset: datetime | None
    secondary_percent: float | None
    secondary_reset: datetime | None


def collect_codex_utilization(
    homes: list[Path],
    *,
    accounts: dict[Path, str] | None = None,
    timezone_name: str = "Europe/Moscow",
    slot_minutes: int = 15,
    threshold_percent: float = 95.0,
    productive_day_hours: float = 8.0,
) -> UtilizationReport:
    """Build a bucketed utilization report for Codex homes."""
    if slot_minutes <= 0 or 1440 % slot_minutes != 0:
        raise ValueError("slot_minutes must divide 1440")

    tz = _load_timezone(timezone_name)

    by_home: dict[str, dict[str, DayBuckets]] = {}
    by_account: dict[str, dict[str, DayBuckets]] = {}
    home_accounts: dict[str, str] = {}
    accounts = accounts or {}

    for home in homes:
        home_key = str(home)
        account_key = accounts.get(home) or "unknown"
        home_accounts[home_key] = account_key
        home_days: dict[str, DayBuckets] = {}
        _collect_home_buckets(
            home,
            tz=tz,
            slot_minutes=slot_minutes,
            threshold_percent=threshold_percent,
            days=home_days,
        )
        by_home[home_key] = home_days
        _merge_days(by_account.setdefault(account_key, {}), home_days)

    return UtilizationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        homes=[str(home) for home in homes],
        timezone=timezone_name,
        slot_minutes=slot_minutes,
        threshold_percent=threshold_percent,
        productive_day_hours=productive_day_hours,
        home_accounts=home_accounts,
        monthly_by_home={
            home: _summarize_months(
                days,
                slot_minutes=slot_minutes,
                productive_day_hours=productive_day_hours,
            )
            for home, days in by_home.items()
        },
        monthly_by_account={
            account: _summarize_months(
                days,
                slot_minutes=slot_minutes,
                productive_day_hours=productive_day_hours,
            )
            for account, days in by_account.items()
        },
    )


def utilization_to_markdown(report: UtilizationReport) -> str:
    """Render a Codex utilization report to Markdown."""
    lines = [
        "# Codex Utilization Report",
        "",
        f"Generated at: `{report.generated_at}`",
        f"Timezone: `{report.timezone}`",
        f"Homes: `{len(report.homes)}`",
        f"Slot size: `{report.slot_minutes}m`",
        f"Limit threshold: `{report.threshold_percent:g}%`",
        f"Productive day cap: `{report.productive_day_hours:g}h`",
    ]

    if not report.monthly_by_account:
        lines.append("_No Codex token events found._")
        return "\n".join(lines)

    for account, monthly in sorted(report.monthly_by_account.items()):
        lines.extend([
            "",
            f"## Account: {account}",
            "",
            "### Monthly Summary",
            "",
            *_summary_table(monthly, report.slot_minutes),
        ])

    return "\n".join(lines)


def _collect_home_buckets(
    home: Path,
    *,
    tz: tzinfo,
    slot_minutes: int,
    threshold_percent: float,
    days: dict[str, DayBuckets],
) -> None:
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return

    for path in sessions_dir.glob("**/*.jsonl"):
        events = list(_read_token_events(path))
        for event in events:
            local_ts = event.timestamp.astimezone(tz)
            day = _day_for(local_ts)
            slot = _slot_for(local_ts, slot_minutes)
            bucket = days.setdefault(day, DayBuckets())
            bucket.active.add(slot)

            if _is_near_limit(event.primary_percent, threshold_percent):
                bucket.near_5h.add(slot)
                _paint_constrained(
                    days,
                    start=event.timestamp,
                    end=event.primary_reset,
                    tz=tz,
                    slot_minutes=slot_minutes,
                    field="constrained_5h",
                )

            if _is_near_limit(event.secondary_percent, threshold_percent):
                bucket.near_weekly.add(slot)
                _paint_constrained(
                    days,
                    start=event.timestamp,
                    end=event.secondary_reset,
                    tz=tz,
                    slot_minutes=slot_minutes,
                    field="constrained_weekly",
                )


def _read_token_events(path: Path) -> list[_TokenEvent]:
    events: list[_TokenEvent] = []
    try:
        lines = path.open(encoding="utf-8")
    except OSError:
        return events

    with lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            payload = entry.get("payload")
            if entry.get("type") != "event_msg" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "token_count":
                continue

            timestamp = _parse_timestamp(entry.get("timestamp"))
            if timestamp is None:
                continue

            rate_limits = payload.get("rate_limits")
            if not isinstance(rate_limits, dict):
                rate_limits = {}

            primary = _as_dict(rate_limits.get("primary"))
            secondary = _as_dict(rate_limits.get("secondary"))
            events.append(_TokenEvent(
                timestamp=timestamp,
                primary_percent=_as_float(primary.get("used_percent")),
                primary_reset=_parse_epoch(primary.get("resets_at")),
                secondary_percent=_as_float(secondary.get("used_percent")),
                secondary_reset=_parse_epoch(secondary.get("resets_at")),
            ))

    return sorted(events, key=lambda event: event.timestamp)


def _paint_constrained(
    days: dict[str, DayBuckets],
    *,
    start: datetime,
    end: datetime | None,
    tz: tzinfo,
    slot_minutes: int,
    field: str,
) -> None:
    if end is None or end <= start:
        return

    current = start.astimezone(tz)
    local_end = end.astimezone(tz)
    while current < local_end:
        day = _day_for(current)
        slot = _slot_for(current, slot_minutes)
        getattr(days.setdefault(day, DayBuckets()), field).add(slot)
        current = _slot_start(current, slot_minutes) + timedelta(minutes=slot_minutes)


def _summarize_months(
    days: dict[str, DayBuckets],
    *,
    slot_minutes: int,
    productive_day_hours: float,
) -> dict[str, MonthSummary]:
    monthly: dict[str, MonthSummary] = {}
    productive_slot_cap = int(productive_day_hours * 60 / slot_minutes)

    for day, buckets in sorted(days.items()):
        month = day[:7]
        summary = monthly.setdefault(month, MonthSummary())
        summary.days += 1

        active_slots = len(buckets.active)
        constrained_5h = len(buckets.constrained_5h)
        constrained_weekly = len(buckets.constrained_weekly)

        summary.active_slots += active_slots
        summary.productive_slots += min(active_slots, productive_slot_cap)
        summary.overhead_slots += max(active_slots - productive_slot_cap, 0)
        summary.constrained_5h_slots += constrained_5h
        summary.constrained_weekly_slots += constrained_weekly
        if buckets.near_5h:
            summary.near_5h_days += 1
        if buckets.near_weekly:
            summary.near_weekly_days += 1

    return monthly


def _summary_table(monthly: dict[str, MonthSummary], slot_minutes: int) -> list[str]:
    if not monthly:
        return ["_No Codex token events found._"]

    rows = [
        [month, *_summary_row(summary, slot_minutes)]
        for month, summary in sorted(monthly.items())
    ]
    return _render_table(
        headers=[
            "Month",
            "Days",
            "Active h",
            "Productive h",
            "Overhead h",
            "Constrained 5h h",
            "Constrained Weekly h",
            "Near 5h Days",
            "Near Weekly Days",
        ],
        rows=rows,
        right_align=set(range(1, 9)),
    )


def _summary_row(summary: MonthSummary, slot_minutes: int) -> list[str]:
    return [
        str(summary.days),
        _format_hours(summary.active_slots, slot_minutes),
        _format_hours(summary.productive_slots, slot_minutes),
        _format_hours(summary.overhead_slots, slot_minutes),
        _format_hours(summary.constrained_5h_slots, slot_minutes),
        _format_hours(summary.constrained_weekly_slots, slot_minutes),
        str(summary.near_5h_days),
        str(summary.near_weekly_days),
    ]


def _merge_days(target: dict[str, DayBuckets], source: dict[str, DayBuckets]) -> None:
    for day, buckets in source.items():
        merged = target.setdefault(day, DayBuckets())
        merged.active.update(buckets.active)
        merged.near_5h.update(buckets.near_5h)
        merged.near_weekly.update(buckets.near_weekly)
        merged.constrained_5h.update(buckets.constrained_5h)
        merged.constrained_weekly.update(buckets.constrained_weekly)


def _load_timezone(timezone_name: str) -> tzinfo:
    if timezone_name == "UTC":
        return timezone.utc
    if timezone_name == "Europe/Moscow":
        return timezone(timedelta(hours=3), name="Europe/Moscow")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone_name}") from exc


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_epoch(value: Any) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _is_near_limit(value: float | None, threshold_percent: float) -> bool:
    return value is not None and value >= threshold_percent


def _day_for(value: datetime) -> str:
    return value.date().isoformat()


def _slot_for(value: datetime, slot_minutes: int) -> int:
    return (value.hour * 60 + value.minute) // slot_minutes


def _slot_start(value: datetime, slot_minutes: int) -> datetime:
    minute = (value.minute // slot_minutes) * slot_minutes
    return value.replace(minute=minute, second=0, microsecond=0)


def _format_hours(slots: int, slot_minutes: int) -> str:
    return f"{slots * slot_minutes / 60:.2f}"
