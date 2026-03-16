"""Orchestrator: combines Codex DB metadata and rollout JSONL into a Report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_report.codex_db import find_state_db, read_threads
from llm_report.models import (
    DailyReport,
    MonthlyReport,
    Report,
    SessionReport,
    TokenUsage,
)
from llm_report.codex_rollout import extract_last_model, parse_rollout


def _parse_source(raw: str) -> tuple[str, str | None]:
    """Parse the source field from DB into (source_category, parent_id).

    Simple strings like "cli", "vscode", "exec", "mcp" are returned as-is.
    JSON strings containing "subagent" are parsed for parent_thread_id.
    """
    if not raw.startswith("{"):
        return (raw, None)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return (raw, None)

    if not isinstance(data, dict):
        return (raw, None)

    if "subagent" in data:
        subagent = data["subagent"]
        if isinstance(subagent, dict):
            for variant in subagent.values():
                if isinstance(variant, dict) and "parent_thread_id" in variant:
                    return ("subagent", variant["parent_thread_id"])
        return ("subagent", None)

    return (raw, None)


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


def collect(codex_home: Path) -> Report:
    """Build a complete report from CODEX_HOME data."""
    db_path = find_state_db(codex_home)
    if db_path is None:
        return _empty_report(codex_home)

    threads = read_threads(db_path)
    sessions: list[SessionReport] = []
    monthly: dict[str, MonthlyReport] = {}
    grand_by_model: dict[str, TokenUsage] = {}

    for thread in threads:
        session = _build_session(thread)
        sessions.append(session)

        # Monthly aggregation
        month_key = session.created_at[:7]  # "YYYY-MM"
        if month_key not in monthly:
            monthly[month_key] = MonthlyReport()
        mr = monthly[month_key]
        mr.session_count += 1
        if session.source == "subagent":
            mr.subagent_count += 1
        _add_usage(mr.by_model, session.usage_by_model)
        mr.total += session.total_usage

        day_key = session.created_at[:10]  # "YYYY-MM-DD"
        if day_key not in mr.daily:
            mr.daily[day_key] = DailyReport()
        dr = mr.daily[day_key]
        dr.session_count += 1
        if session.source == "subagent":
            dr.subagent_count += 1
        _add_usage(dr.by_model, session.usage_by_model)
        dr.total += session.total_usage

        # Grand total
        _add_usage(grand_by_model, session.usage_by_model)

    return Report(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_home=str(codex_home),
        provider="codex",
        sessions=sessions,
        monthly=monthly,
        grand_total_by_model=grand_by_model,
        grand_total=_sum_usage(grand_by_model),
    )


def _build_session(thread: dict[str, Any]) -> SessionReport:
    """Build a SessionReport from a DB thread row."""
    source, parent_id = _parse_source(thread["source"])
    rollout_path = Path(thread["rollout_path"])
    tokens_used = thread["tokens_used"]

    usage_by_model: dict[str, TokenUsage] = {}

    if rollout_path.exists():
        usage_by_model = parse_rollout(rollout_path)
        if not usage_by_model and tokens_used > 0:
            model = extract_last_model(rollout_path)
            usage_by_model = {model: TokenUsage(total_tokens=tokens_used)}
    elif tokens_used > 0:
        usage_by_model = {"unknown": TokenUsage(total_tokens=tokens_used)}

    return SessionReport(
        id=thread["id"],
        title=thread["title"],
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
        source=source,
        parent_id=parent_id,
        agent_nickname=thread["agent_nickname"],
        agent_role=thread["agent_role"],
        model_provider=thread["model_provider"],
        usage_by_model=usage_by_model,
        total_usage=_sum_usage(usage_by_model),
    )


def _empty_report(codex_home: Path) -> Report:
    return Report(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_home=str(codex_home),
        provider="codex",
        sessions=[],
        monthly={},
        grand_total_by_model={},
        grand_total=TokenUsage(),
    )
