"""Helpers for combining multiple home reports into one summary."""

from __future__ import annotations

from datetime import datetime, timezone

from llm_report.models import CombinedReport, DailyReport, MonthlyReport, Report, TokenUsage


def combine_reports(reports: list[Report]) -> CombinedReport:
    """Combine multiple single-home reports into one aggregate report."""
    monthly: dict[str, MonthlyReport] = {}
    grand_total_by_model: dict[str, TokenUsage] = {}
    grand_total = TokenUsage()
    session_count = 0
    subagent_count = 0

    for report in reports:
        session_count += len(report.sessions)
        subagent_count += sum(month.subagent_count for month in report.monthly.values())
        grand_total += report.grand_total
        _add_usage(grand_total_by_model, report.grand_total_by_model)

        for month_key, month in report.monthly.items():
            target = monthly.setdefault(month_key, MonthlyReport())
            _merge_monthly(target, month)

    return CombinedReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        homes=reports,
        monthly=monthly,
        grand_total_by_model=grand_total_by_model,
        grand_total=grand_total,
        session_count=session_count,
        subagent_count=subagent_count,
    )


def _merge_monthly(target: MonthlyReport, source: MonthlyReport) -> None:
    target.session_count += source.session_count
    target.subagent_count += source.subagent_count
    target.total += source.total
    _add_usage(target.by_model, source.by_model)

    for day_key, day in source.daily.items():
        target_day = target.daily.setdefault(day_key, DailyReport())
        target_day.session_count += day.session_count
        target_day.subagent_count += day.subagent_count
        target_day.total += day.total
        _add_usage(target_day.by_model, day.by_model)


def _add_usage(target: dict[str, TokenUsage], source: dict[str, TokenUsage]) -> None:
    for model, usage in source.items():
        if model not in target:
            target[model] = TokenUsage()
        target[model] += usage
