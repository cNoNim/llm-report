"""Orchestrator for Claude Code usage reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from llm_report.claude_sessions import (
    _resolve_session_jsonl,
    build_session_report,
    find_all_sessions,
    parse_session_jsonl,
)
from llm_report.models import (
    DailyReport,
    MonthlyReport,
    Report,
    SessionReport,
    TokenUsage,
)


def _add_usage(target: dict[str, TokenUsage], source: dict[str, TokenUsage]) -> None:
    """Merge source usage into target, summing per model."""
    for model, usage in source.items():
        if model not in target:
            target[model] = TokenUsage()
        target[model] += usage


def _sum_usage(by_model: dict[str, TokenUsage]) -> TokenUsage:
    """Sum all per-model usage into a single total."""
    total = TokenUsage()
    for usage in by_model.values():
        total += usage
    return total


def claude_collect(claude_home: Path) -> Report:
    """Build a complete report from Claude Code JSONL session files."""
    entries = find_all_sessions(claude_home)

    sessions: list[SessionReport] = []
    monthly: dict[str, MonthlyReport] = {}
    grand_by_model: dict[str, TokenUsage] = {}

    for entry in entries:
        jsonl_path = _resolve_session_jsonl(entry)
        if jsonl_path is not None:
            usage = parse_session_jsonl(jsonl_path)
        else:
            usage = {}

        session = build_session_report(entry, usage)
        sessions.append(session)

        created = session.created_at
        if not created:
            continue

        month_key = created[:7]  # "YYYY-MM"
        if month_key not in monthly:
            monthly[month_key] = MonthlyReport()
        mr = monthly[month_key]
        mr.session_count += 1
        if session.source == "subagent":
            mr.subagent_count += 1
        _add_usage(mr.by_model, session.usage_by_model)
        mr.total += session.total_usage

        day_key = created[:10]  # "YYYY-MM-DD"
        if day_key not in mr.daily:
            mr.daily[day_key] = DailyReport()
        dr = mr.daily[day_key]
        dr.session_count += 1
        if session.source == "subagent":
            dr.subagent_count += 1
        _add_usage(dr.by_model, session.usage_by_model)
        dr.total += session.total_usage

        _add_usage(grand_by_model, session.usage_by_model)

    return Report(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_home=str(claude_home),
        provider="claude",
        sessions=sessions,
        monthly=monthly,
        grand_total_by_model=grand_by_model,
        grand_total=_sum_usage(grand_by_model),
    )
