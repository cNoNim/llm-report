"""Tests for combining multiple home reports."""

from llm_report.aggregate import combine_reports
from llm_report.models import MonthlyReport, Report, SessionReport, TokenUsage


def test_combine_reports_sums_totals_and_months():
    openai_report = Report(
        generated_at="2026-03-16T10:00:00+00:00",
        data_home="/tmp/codex-a",
        provider="codex",
        sessions=[
            SessionReport(
                id="codex-1",
                title="Codex",
                created_at="2026-03-01T00:00:00+00:00",
                updated_at="2026-03-01T00:00:00+00:00",
                source="cli",
                parent_id=None,
                agent_nickname=None,
                agent_role=None,
                model_provider="openai",
                usage_by_model={},
                total_usage=TokenUsage(),
            ),
        ],
        monthly={
            "2026-03": MonthlyReport(
                by_model={"gpt-5.4": TokenUsage(total_tokens=100)},
                total=TokenUsage(total_tokens=100),
                session_count=1,
                subagent_count=0,
            ),
        },
        grand_total_by_model={"gpt-5.4": TokenUsage(total_tokens=100)},
        grand_total=TokenUsage(total_tokens=100),
    )
    claude_report = Report(
        generated_at="2026-03-16T10:00:00+00:00",
        data_home="/tmp/claude-a",
        provider="claude",
        sessions=[
            SessionReport(
                id="claude-1",
                title="Claude 1",
                created_at="2026-03-01T00:00:00+00:00",
                updated_at="2026-03-01T00:00:00+00:00",
                source="cli",
                parent_id=None,
                agent_nickname=None,
                agent_role=None,
                model_provider="anthropic",
                usage_by_model={},
                total_usage=TokenUsage(),
            ),
            SessionReport(
                id="claude-2",
                title="Claude 2",
                created_at="2026-04-01T00:00:00+00:00",
                updated_at="2026-04-01T00:00:00+00:00",
                source="subagent",
                parent_id=None,
                agent_nickname=None,
                agent_role=None,
                model_provider="anthropic",
                usage_by_model={},
                total_usage=TokenUsage(),
            ),
        ],
        monthly={
            "2026-03": MonthlyReport(
                by_model={"claude-sonnet-4-6": TokenUsage(total_tokens=250)},
                total=TokenUsage(total_tokens=250),
                session_count=2,
                subagent_count=1,
            ),
            "2026-04": MonthlyReport(
                by_model={"claude-opus-4-6": TokenUsage(total_tokens=50)},
                total=TokenUsage(total_tokens=50),
                session_count=1,
                subagent_count=0,
            ),
        },
        grand_total_by_model={
            "claude-sonnet-4-6": TokenUsage(total_tokens=250),
            "claude-opus-4-6": TokenUsage(total_tokens=50),
        },
        grand_total=TokenUsage(total_tokens=300),
    )

    combined = combine_reports([openai_report, claude_report])

    assert combined.provider == "combined"
    assert len(combined.homes) == 2
    assert combined.session_count == 3
    assert combined.subagent_count == 1
    assert combined.grand_total.total_tokens == 400
    assert combined.monthly["2026-03"].total.total_tokens == 350
    assert combined.monthly["2026-03"].session_count == 3
    assert combined.monthly["2026-03"].subagent_count == 1
    assert combined.monthly["2026-04"].total.total_tokens == 50
