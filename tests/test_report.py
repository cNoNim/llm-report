"""Tests for report rendering."""

from llm_report.aggregate import combine_reports
from llm_report.models import DailyReport, MonthlyReport, Report, SessionReport, TokenUsage
from llm_report.pricing import ModelPricing, PricingCatalog
from llm_report.report import report_to_dict, report_to_markdown


def test_report_to_markdown_renders_monthly_summary():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/codex-home",
        sessions=[
            SessionReport(
                id="s1",
                title="Session 1",
                created_at="2026-03-01T10:00:00+00:00",
                updated_at="2026-03-01T10:05:00+00:00",
                source="cli",
                parent_id=None,
                agent_nickname=None,
                agent_role=None,
                model_provider="openai",
                usage_by_model={"gpt-5.4": TokenUsage(total_tokens=120)},
                total_usage=TokenUsage(total_tokens=120),
            ),
        ],
        monthly={
            "2026-02": MonthlyReport(
                by_model={"gpt-5.3-codex": TokenUsage(input_tokens=100, total_tokens=120)},
                total=TokenUsage(input_tokens=100, total_tokens=120),
                session_count=1,
                subagent_count=0,
            ),
            "2026-03": MonthlyReport(
                by_model={
                    "gpt-5.4": TokenUsage(
                        input_tokens=200,
                        cached_input_tokens=50,
                        output_tokens=30,
                        reasoning_output_tokens=10,
                        total_tokens=230,
                    ),
                    "o3": TokenUsage(
                        input_tokens=10,
                        output_tokens=5,
                        total_tokens=15,
                    ),
                },
                total=TokenUsage(
                    input_tokens=210,
                    cached_input_tokens=50,
                    output_tokens=35,
                    reasoning_output_tokens=10,
                    total_tokens=245,
                ),
                session_count=2,
                subagent_count=1,
            ),
        },
        grand_total_by_model={
            "gpt-5.3-codex": TokenUsage(input_tokens=100, total_tokens=120),
            "gpt-5.4": TokenUsage(
                input_tokens=200,
                cached_input_tokens=50,
                output_tokens=30,
                reasoning_output_tokens=10,
                total_tokens=230,
            ),
            "o3": TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        },
        grand_total=TokenUsage(
            input_tokens=310,
            cached_input_tokens=50,
            output_tokens=35,
            reasoning_output_tokens=10,
            total_tokens=365,
        ),
    )

    markdown = report_to_markdown(report)

    assert "# Codex Usage Report" in markdown
    assert "## Monthly Summary" in markdown
    assert "| Month   | Sessions | Subagents | Total Tokens | Uncached Input | Cached Input | Output | Reasoning |" in markdown
    assert "| ------- | -------: | --------: | -----------: | -------------: | -----------: | -----: | --------: |" in markdown
    assert "| 2026-02 |        1 |         0 |          120 |            100 |            0 |      0 |         0 |" in markdown
    assert "| 2026-03 |        2 |         1 |          245 |            160 |           50 |     35 |        10 |" in markdown
    assert "## 2026-03" in markdown
    assert "| Model   | Total Tokens | Uncached Input | Cached Input | Output | Reasoning |" in markdown
    assert "| gpt-5.4 |          230 |            150 |           50 |     30 |        10 |" in markdown
    assert "| o3      |           15 |             10 |            0 |      5 |         0 |" in markdown


def test_report_to_markdown_renders_gemini_title_and_home_label():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/gemini-home",
        provider="gemini",
        sessions=[],
        monthly={},
        grand_total_by_model={},
        grand_total=TokenUsage(),
    )

    markdown = report_to_markdown(report)

    assert "# Gemini CLI Usage Report" in markdown
    assert "GEMINI_HOME: `/tmp/gemini-home`" in markdown


def test_report_to_markdown_renders_gemini_pricing_and_tool_exclusion():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/gemini-home",
        provider="gemini",
        sessions=[],
        monthly={
            "2026-03": MonthlyReport(
                by_model={
                    "gemini-2.5-pro": TokenUsage(
                        input_tokens=1_000_000,
                        cached_input_tokens=200_000,
                        output_tokens=120_000,
                        reasoning_output_tokens=20_000,
                        tool_tokens=50_000,
                        total_tokens=1_170_000,
                    ),
                },
                total=TokenUsage(
                    input_tokens=1_000_000,
                    cached_input_tokens=200_000,
                    output_tokens=120_000,
                    reasoning_output_tokens=20_000,
                    tool_tokens=50_000,
                    total_tokens=1_170_000,
                ),
                session_count=1,
                subagent_count=0,
            ),
        },
        grand_total_by_model={
            "gemini-2.5-pro": TokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=200_000,
                output_tokens=120_000,
                reasoning_output_tokens=20_000,
                tool_tokens=50_000,
                total_tokens=1_170_000,
            ),
        },
        grand_total=TokenUsage(
            input_tokens=1_000_000,
            cached_input_tokens=200_000,
            output_tokens=120_000,
            reasoning_output_tokens=20_000,
            tool_tokens=50_000,
            total_tokens=1_170_000,
        ),
    )
    pricing = PricingCatalog(
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
        extracted_at="2026-03-16T15:00:00+00:00",
        unit="usd_per_1m_tokens",
        models={
            "gemini-2.5-pro": ModelPricing(input=1.25, cached_input=0.125, output=10.0),
        },
    )

    markdown = report_to_markdown(report, pricing)

    assert "Estimated cost: `$2.22`" in markdown
    assert "**Pricing Source**" in markdown
    assert "- `https://ai.google.dev/gemini-api/docs/pricing`" in markdown
    assert "Tool tokens excluded from estimated cost: `50,000`" in markdown


def test_report_to_markdown_formats_large_numbers():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/codex-home",
        sessions=[],
        monthly={
            "2026-03": MonthlyReport(
                by_model={"gpt-5.4": TokenUsage(total_tokens=1234567)},
                total=TokenUsage(total_tokens=1234567),
                session_count=3,
                subagent_count=1,
            ),
        },
        grand_total_by_model={"gpt-5.4": TokenUsage(total_tokens=1234567)},
        grand_total=TokenUsage(total_tokens=1234567),
    )

    markdown = report_to_markdown(report)

    assert "`1,234,567`" in markdown
    assert "| 2026-03 |        3 |         1 |    1,234,567 |              0 |            0 |      0 |         0 |" in markdown


def test_report_to_markdown_renders_costs_when_pricing_present():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/codex-home",
        sessions=[],
        monthly={
            "2026-03": MonthlyReport(
                by_model={
                    "gpt-5.4": TokenUsage(
                        input_tokens=1_000_000,
                        cached_input_tokens=200_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                    "o3": TokenUsage(
                        input_tokens=500_000,
                        output_tokens=50_000,
                        total_tokens=550_000,
                    ),
                },
                total=TokenUsage(
                    input_tokens=1_500_000,
                    cached_input_tokens=200_000,
                    output_tokens=150_000,
                    total_tokens=1_650_000,
                ),
                session_count=2,
                subagent_count=0,
            ),
        },
        grand_total_by_model={
            "gpt-5.4": TokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=200_000,
                output_tokens=100_000,
                total_tokens=1_100_000,
            ),
            "o3": TokenUsage(
                input_tokens=500_000,
                output_tokens=50_000,
                total_tokens=550_000,
            ),
        },
        grand_total=TokenUsage(
            input_tokens=1_500_000,
            cached_input_tokens=200_000,
            output_tokens=150_000,
            total_tokens=1_650_000,
        ),
    )
    pricing = PricingCatalog(
        source_url="https://developers.openai.com/api/docs/pricing/",
        extracted_at="2026-03-16T15:00:00+00:00",
        unit="usd_per_1m_tokens",
        models={
            "gpt-5.4": ModelPricing(input=2.5, cached_input=0.25, output=15.0),
            "o3": ModelPricing(input=2.0, cached_input=0.5, output=8.0),
        },
    )

    markdown = report_to_markdown(report, pricing)

    assert "Estimated cost: `$4.95`" in markdown
    assert "**Pricing Source**" in markdown
    assert "- `https://developers.openai.com/api/docs/pricing/`" in markdown
    assert "Input USD" in markdown
    assert "Cached USD" in markdown
    assert "Output USD" in markdown
    assert "Total USD" in markdown
    assert "| 2026-03 |        2 |         0 |    1,650,000 |      1,300,000 |      200,000 | 150,000 |         0 |     $3.00 |      $0.05 |      $1.90 |     $4.95 |" in markdown
    assert "| gpt-5.4 |    1,100,000 |        800,000 |      200,000 | 100,000 |         0 |     $2.00 |      $0.05 |      $1.50 |     $3.55 |" in markdown
    assert "| o3      |      550,000 |        500,000 |            0 |  50,000 |         0 |     $1.00 |      $0.00 |      $0.40 |     $1.40 |" in markdown


def test_report_to_markdown_keeps_partial_cost_when_some_models_unpriced():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/codex-home",
        sessions=[],
        monthly={
            "2026-03": MonthlyReport(
                by_model={
                    "gpt-5.4": TokenUsage(
                        input_tokens=1_000_000,
                        cached_input_tokens=200_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                    "mystery-model": TokenUsage(
                        input_tokens=500_000,
                        output_tokens=50_000,
                        total_tokens=550_000,
                    ),
                },
                total=TokenUsage(
                    input_tokens=1_500_000,
                    cached_input_tokens=200_000,
                    output_tokens=150_000,
                    total_tokens=1_650_000,
                ),
                session_count=2,
                subagent_count=0,
            ),
        },
        grand_total_by_model={
            "gpt-5.4": TokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=200_000,
                output_tokens=100_000,
                total_tokens=1_100_000,
            ),
            "mystery-model": TokenUsage(
                input_tokens=500_000,
                output_tokens=50_000,
                total_tokens=550_000,
            ),
        },
        grand_total=TokenUsage(
            input_tokens=1_500_000,
            cached_input_tokens=200_000,
            output_tokens=150_000,
            total_tokens=1_650_000,
        ),
    )
    pricing = PricingCatalog(
        source_url="https://developers.openai.com/api/docs/pricing/",
        extracted_at="2026-03-16T15:00:00+00:00",
        unit="usd_per_1m_tokens",
        models={
            "gpt-5.4": ModelPricing(input=2.5, cached_input=0.25, output=15.0),
        },
    )

    markdown = report_to_markdown(report, pricing)

    assert "Estimated cost: `$3.55`" in markdown
    assert "Unpriced models: `mystery-model`" in markdown
    assert "| 2026-03 |        2 |         0 |    1,650,000 |      1,300,000 |      200,000 | 150,000 |         0 |     $2.00 |      $0.05 |      $1.50 |     $3.55 |" in markdown
    assert "| mystery-model |      550,000 |        500,000 |            0 |  50,000 |         0 |       N/A |        N/A |        N/A |       N/A |" in markdown


def test_report_to_dict_includes_daily_breakdown():
    report = Report(
        generated_at="2026-03-16T14:37:06+00:00",
        data_home="/tmp/codex-home",
        sessions=[],
        monthly={
            "2026-03": MonthlyReport(
                total=TokenUsage(total_tokens=120),
                session_count=1,
                daily={
                    "2026-03-18": DailyReport(
                        total=TokenUsage(total_tokens=120),
                        session_count=1,
                    ),
                },
            ),
        },
        grand_total_by_model={},
        grand_total=TokenUsage(total_tokens=120),
    )

    payload = report_to_dict(report)

    assert payload["monthly"]["2026-03"]["daily"]["2026-03-18"]["total"]["total_tokens"] == 120
    assert payload["monthly"]["2026-03"]["daily"]["2026-03-18"]["session_count"] == 1


def test_combined_report_to_markdown_renders_home_summary():
    combined = combine_reports([
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/codex-home",
            provider="codex",
            sessions=[
                SessionReport(
                    id="codex-1",
                    title="Codex",
                    created_at="2026-03-01T10:00:00+00:00",
                    updated_at="2026-03-01T10:05:00+00:00",
                    source="cli",
                    parent_id=None,
                    agent_nickname=None,
                    agent_role=None,
                    model_provider="openai",
                    usage_by_model={"gpt-5.4": TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120)},
                    total_usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
                ),
            ],
            monthly={
                "2026-03": MonthlyReport(
                    by_model={"gpt-5.4": TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120)},
                    total=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
                    session_count=1,
                    subagent_count=0,
                ),
            },
            grand_total_by_model={"gpt-5.4": TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120)},
            grand_total=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        ),
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/claude-home",
            provider="claude",
            sessions=[
                SessionReport(
                    id="claude-1",
                    title="Claude",
                    created_at="2026-03-02T10:00:00+00:00",
                    updated_at="2026-03-02T10:05:00+00:00",
                    source="subagent",
                    parent_id=None,
                    agent_nickname=None,
                    agent_role=None,
                    model_provider="anthropic",
                    usage_by_model={"claude-sonnet-4-6": TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80)},
                    total_usage=TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80),
                ),
            ],
            monthly={
                "2026-03": MonthlyReport(
                    by_model={"claude-sonnet-4-6": TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80)},
                    total=TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80),
                    session_count=1,
                    subagent_count=1,
                ),
            },
            grand_total_by_model={"claude-sonnet-4-6": TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80)},
            grand_total=TokenUsage(input_tokens=60, output_tokens=20, total_tokens=80),
        ),
    ])

    markdown = report_to_markdown(combined)

    assert "# Combined Usage Report" in markdown
    assert "## Home Summary" in markdown
    assert "| Provider | Home" in markdown
    assert "| codex" in markdown
    assert "/tmp/codex-home" in markdown
    assert "| claude" in markdown
    assert "/tmp/claude-home" in markdown
    assert "## Model Summary" in markdown
    assert "| Provider | Model" in markdown
    assert "gpt-5.4" in markdown
    assert "claude-sonnet-4-6" in markdown
    assert "| Month   | Sessions | Input | Output |" in markdown
    assert "| 2026-03 |        2 |   160 |     40 |" in markdown


def test_combined_report_to_dict_includes_homes():
    combined = combine_reports([
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/codex-home",
            provider="codex",
            sessions=[],
            monthly={},
            grand_total_by_model={},
            grand_total=TokenUsage(),
        ),
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/claude-home",
            provider="claude",
            sessions=[],
            monthly={},
            grand_total_by_model={},
            grand_total=TokenUsage(),
        ),
    ])

    payload = report_to_dict(combined)

    assert payload["provider"] == "combined"
    assert payload["home_count"] == 2
    assert [home["provider"] for home in payload["homes"]] == ["codex", "claude"]


def test_combined_report_to_markdown_renders_provider_pricing():
    combined = combine_reports([
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/codex-home",
            provider="codex",
            sessions=[
                SessionReport(
                    id="codex-1",
                    title="Codex",
                    created_at="2026-03-01T10:00:00+00:00",
                    updated_at="2026-03-01T10:05:00+00:00",
                    source="cli",
                    parent_id=None,
                    agent_nickname=None,
                    agent_role=None,
                    model_provider="openai",
                    usage_by_model={
                        "gpt-5.4": TokenUsage(
                            input_tokens=1_000_000,
                            cached_input_tokens=200_000,
                            output_tokens=100_000,
                            total_tokens=1_100_000,
                        ),
                    },
                    total_usage=TokenUsage(
                        input_tokens=1_000_000,
                        cached_input_tokens=200_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                ),
            ],
            monthly={
                "2026-03": MonthlyReport(
                    by_model={
                        "gpt-5.4": TokenUsage(
                            input_tokens=1_000_000,
                            cached_input_tokens=200_000,
                            output_tokens=100_000,
                            total_tokens=1_100_000,
                        ),
                    },
                    total=TokenUsage(
                        input_tokens=1_000_000,
                        cached_input_tokens=200_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                    session_count=1,
                    subagent_count=0,
                ),
            },
            grand_total_by_model={
                "gpt-5.4": TokenUsage(
                    input_tokens=1_000_000,
                    cached_input_tokens=200_000,
                    output_tokens=100_000,
                    total_tokens=1_100_000,
                ),
            },
            grand_total=TokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=200_000,
                output_tokens=100_000,
                total_tokens=1_100_000,
            ),
        ),
        Report(
            generated_at="2026-03-16T14:37:06+00:00",
            data_home="/tmp/claude-home",
            provider="claude",
            sessions=[
                SessionReport(
                    id="claude-1",
                    title="Claude",
                    created_at="2026-03-01T10:00:00+00:00",
                    updated_at="2026-03-01T10:05:00+00:00",
                    source="cli",
                    parent_id=None,
                    agent_nickname=None,
                    agent_role=None,
                    model_provider="anthropic",
                    usage_by_model={
                        "claude-sonnet-4-6": TokenUsage(
                            input_tokens=1_000_000,
                            output_tokens=100_000,
                            total_tokens=1_100_000,
                        ),
                    },
                    total_usage=TokenUsage(
                        input_tokens=1_000_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                ),
            ],
            monthly={
                "2026-03": MonthlyReport(
                    by_model={
                        "claude-sonnet-4-6": TokenUsage(
                            input_tokens=1_000_000,
                            output_tokens=100_000,
                            total_tokens=1_100_000,
                        ),
                    },
                    total=TokenUsage(
                        input_tokens=1_000_000,
                        output_tokens=100_000,
                        total_tokens=1_100_000,
                    ),
                    session_count=1,
                    subagent_count=0,
                ),
            },
            grand_total_by_model={
                "claude-sonnet-4-6": TokenUsage(
                    input_tokens=1_000_000,
                    output_tokens=100_000,
                    total_tokens=1_100_000,
                ),
            },
            grand_total=TokenUsage(
                input_tokens=1_000_000,
                output_tokens=100_000,
                total_tokens=1_100_000,
            ),
        ),
    ])
    pricing = {
        "codex": PricingCatalog(
            source_url="https://example.com/openai",
            extracted_at=None,
            unit="usd_per_1m_tokens",
            models={"gpt-5.4": ModelPricing(input=2.5, cached_input=0.25, output=15.0)},
        ),
        "claude": PricingCatalog(
            source_url="https://example.com/anthropic",
            extracted_at=None,
            unit="usd_per_1m_tokens",
            models={"claude-sonnet-4-6": ModelPricing(input=3.0, cached_input=0.3, output=15.0)},
        ),
    }

    markdown = report_to_markdown(combined, pricing)

    assert "Estimated cost: `$8.05`" in markdown
    assert "**Pricing Sources**" in markdown
    assert "- `claude` -> `https://example.com/anthropic`" in markdown
    assert "- `codex` -> `https://example.com/openai`" in markdown
    assert "| Provider | Home             | Sessions |     Input |  Output | Total USD |" in markdown
    assert "| codex    | /tmp/codex-home  |        1 | 1,000,000 | 100,000 |     $3.55 |" in markdown
    assert "| claude   | /tmp/claude-home |        1 | 1,000,000 | 100,000 |     $4.50 |" in markdown
    assert "## Model Summary" in markdown
    assert "| Provider | Model" in markdown
    assert "gpt-5.4" in markdown
    assert "claude-sonnet-4-6" in markdown
    assert "1,000,000 | 100,000 |     $3.55 |" in markdown
    assert "1,000,000 | 100,000 |     $4.50 |" in markdown
    assert "| Month   | Sessions |     Input |  Output | Total USD |" in markdown
    assert "| 2026-03 |        2 | 2,000,000 | 200,000 |     $8.05 |" in markdown
