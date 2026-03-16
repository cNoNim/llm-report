"""Report serialization to JSON and Markdown."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from llm_report.models import CombinedReport, MonthlyReport, Report, TokenUsage
from llm_report.pricing import (
    CostBreakdown,
    PricingCatalog,
    estimate_by_model_breakdowns,
    estimate_by_model_costs,
    sum_cost_breakdowns,
    sum_costs,
)

PricingInput = PricingCatalog | dict[str, PricingCatalog] | None


def report_to_dict(report: Report | CombinedReport) -> dict[str, Any]:
    """Convert a report to a JSON-serializable dict."""
    if isinstance(report, CombinedReport):
        return {
            "generated_at": report.generated_at,
            "provider": report.provider,
            "home_count": len(report.homes),
            "session_count": report.session_count,
            "subagent_count": report.subagent_count,
            "homes": [_single_report_to_dict(home) for home in report.homes],
            "monthly": {
                key: _monthly_to_dict(value)
                for key, value in sorted(report.monthly.items())
            },
            "grand_total": {
                "by_model": {
                    key: asdict(value)
                    for key, value in sorted(report.grand_total_by_model.items())
                },
                "total": asdict(report.grand_total),
            },
        }

    return _single_report_to_dict(report)


def _single_report_to_dict(report: Report) -> dict[str, Any]:
    return {
        "generated_at": report.generated_at,
        "data_home": report.data_home,
        "provider": report.provider,
        "sessions": [_session_to_dict(session) for session in report.sessions],
        "monthly": {
            key: _monthly_to_dict(value)
            for key, value in sorted(report.monthly.items())
        },
        "grand_total": {
            "by_model": {
                key: asdict(value)
                for key, value in sorted(report.grand_total_by_model.items())
            },
            "total": asdict(report.grand_total),
        },
    }


def _session_to_dict(session: Any) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "source": session.source,
        "parent_id": session.parent_id,
        "agent_nickname": session.agent_nickname,
        "agent_role": session.agent_role,
        "model_provider": session.model_provider,
        "usage_by_model": {
            key: asdict(value)
            for key, value in sorted(session.usage_by_model.items())
        },
        "total_usage": asdict(session.total_usage),
    }


def _monthly_to_dict(month: Any) -> dict[str, Any]:
    return {
        "by_model": {
            key: asdict(value)
            for key, value in sorted(month.by_model.items())
        },
        "total": asdict(month.total),
        "session_count": month.session_count,
        "subagent_count": month.subagent_count,
        "daily": {
            key: _daily_to_dict(value)
            for key, value in sorted(month.daily.items())
        },
    }


def _daily_to_dict(day: Any) -> dict[str, Any]:
    return {
        "by_model": {
            key: asdict(value)
            for key, value in sorted(day.by_model.items())
        },
        "total": asdict(day.total),
        "session_count": day.session_count,
        "subagent_count": day.subagent_count,
    }


def report_to_json(report: Report | CombinedReport) -> str:
    """Serialize a report to a JSON string."""
    return json.dumps(report_to_dict(report), indent=2, ensure_ascii=False)


def report_to_markdown(
    report: Report | CombinedReport,
    pricing: PricingInput = None,
) -> str:
    """Render a human-friendly Markdown summary."""
    if isinstance(report, CombinedReport):
        return _combined_report_to_markdown(report, pricing)
    return _single_report_to_markdown(report, pricing)


def _single_report_to_markdown(
    report: Report,
    pricing: PricingInput = None,
) -> str:
    catalog = _pricing_for_provider(pricing, report.provider)
    show_cache_creation = report.provider == "claude" and _has_cache_creation(report.grand_total_by_model)

    monthly_rows: list[list[str]] = []
    for month, monthly_report in sorted(report.monthly.items()):
        breakdown, _ = _estimate_cost_breakdown(monthly_report.by_model, catalog)
        monthly_rows.append(
            _summary_row(
                label=month,
                usage=monthly_report.total,
                session_count=monthly_report.session_count,
                subagent_count=monthly_report.subagent_count,
                show_cache_creation=show_cache_creation,
                include_pricing=catalog is not None,
                cost_breakdown=breakdown,
            ),
        )

    title = _single_report_title(report.provider)
    home_label = _single_home_label(report.provider)

    lines = [
        title,
        "",
        f"Generated at: `{report.generated_at}`",
        f"{home_label}: `{report.data_home}`",
        f"Sessions: `{len(report.sessions)}`",
        f"Total tokens: `{_format_int(report.grand_total.total_tokens)}`",
    ]

    lines.extend(_single_pricing_summary_lines(report.grand_total_by_model, catalog, report.provider))
    lines.extend(_monthly_summary_section(monthly_rows, catalog is not None, show_cache_creation))

    for month, monthly_report in sorted(report.monthly.items()):
        lines.extend(
            _monthly_breakdown_to_markdown(
                month,
                monthly_report,
                catalog,
                show_cache_creation,
            ),
        )

    return "\n".join(lines)


def _combined_report_to_markdown(
    report: CombinedReport,
    pricing: PricingInput = None,
) -> str:
    providers = sorted({home.provider for home in report.homes})
    provider_catalogs = {
        provider: catalog
        for provider in providers
        if (catalog := _pricing_for_provider(pricing, provider)) is not None
    }
    include_pricing = bool(provider_catalogs)

    lines = [
        "# Combined Usage Report",
        "",
        f"Generated at: `{report.generated_at}`",
        f"Providers: {_format_code_list(providers)}",
        f"Homes: `{len(report.homes)}`",
        f"Sessions: `{report.session_count}`",
        f"Subagents: `{report.subagent_count}`",
        f"Total tokens: `{_format_int(report.grand_total.total_tokens)}`",
    ]

    lines.extend(_combined_pricing_summary_lines(report.homes, pricing))

    home_rows = []
    for home in sorted(report.homes, key=lambda item: (item.provider, item.data_home)):
        breakdown, _ = _estimate_cost_breakdown(
            home.grand_total_by_model,
            _pricing_for_provider(pricing, home.provider),
        )
        home_rows.append(_combined_home_row(home, include_pricing, breakdown))

    lines.extend([
        "",
        "## Home Summary",
        "",
        *_render_table(
            headers=_combined_home_headers(include_pricing),
            rows=home_rows,
            right_align=_combined_home_right_align(include_pricing),
        ),
    ])

    model_rows = _combined_model_rows(report.homes, pricing)
    lines.extend([
        "",
        "## Model Summary",
        "",
        *_render_table(
            headers=_combined_model_headers(include_pricing),
            rows=model_rows,
            right_align=_combined_model_right_align(include_pricing),
        ),
    ])

    monthly_rows: list[list[str]] = []
    for month, monthly_report in sorted(report.monthly.items()):
        breakdown, _ = _combined_month_cost_breakdown(report.homes, month, pricing)
        monthly_rows.append(_combined_month_row(month, monthly_report, include_pricing, breakdown))

    lines.extend(_combined_monthly_summary_section(monthly_rows, include_pricing))

    return "\n".join(lines)


def _single_pricing_summary_lines(
    usage_by_model: dict[str, TokenUsage],
    catalog: PricingCatalog | None,
    provider: str | None = None,
) -> list[str]:
    if catalog is None:
        return []

    breakdown, missing_models = _estimate_cost_breakdown(usage_by_model, catalog)
    lines = [f"Estimated cost: `{_format_usd(_total_cost(breakdown))}`"]
    if catalog.source_url:
        lines.extend([
            "",
            "**Pricing Source**",
            f"- `{catalog.source_url}`",
        ])
    if provider == "gemini":
        tool_tokens = _sum_tool_tokens(usage_by_model)
        if tool_tokens > 0:
            lines.append(f"Tool tokens excluded from estimated cost: `{_format_int(tool_tokens)}`")
    if missing_models:
        lines.append(f"Unpriced models: {_format_code_list(missing_models)}")
    return lines


def _combined_pricing_summary_lines(
    reports: list[Report],
    pricing: PricingInput,
) -> list[str]:
    provider_catalogs = {
        provider: catalog
        for provider in sorted({report.provider for report in reports})
        if (catalog := _pricing_for_provider(pricing, provider)) is not None
    }
    if not provider_catalogs:
        return []

    breakdown, missing_models = _combined_cost_breakdown(
        reports,
        pricing,
        lambda report: report.grand_total_by_model,
    )
    lines = [f"Estimated cost: `{_format_usd(_total_cost(breakdown))}`"]

    source_parts = [
        f"- `{provider}` -> `{catalog.source_url}`"
        for provider, catalog in provider_catalogs.items()
        if catalog.source_url
    ]
    if source_parts:
        lines.extend([
            "",
            "**Pricing Sources**",
            *source_parts,
        ])
    gemini_tool_tokens = sum(
        _sum_tool_tokens(report.grand_total_by_model)
        for report in reports
        if report.provider == "gemini"
    )
    if gemini_tool_tokens > 0:
        lines.append(f"Gemini tool tokens excluded from estimated cost: `{_format_int(gemini_tool_tokens)}`")
    if missing_models:
        lines.append(f"Unpriced models: {_format_code_list(missing_models)}")
    return lines


def _combined_month_cost_breakdown(
    reports: list[Report],
    month: str,
    pricing: PricingInput,
) -> tuple[CostBreakdown | None, list[str]]:
    return _combined_cost_breakdown(
        [report for report in reports if month in report.monthly],
        pricing,
        lambda report: report.monthly[month].by_model,
    )


def _combined_cost_breakdown(
    reports: list[Report],
    pricing: PricingInput,
    usage_getter: Any,
) -> tuple[CostBreakdown | None, list[str]]:
    breakdowns: dict[str, CostBreakdown | None] = {}
    missing_models: set[str] = set()

    for index, report in enumerate(reports):
        usage_by_model = usage_getter(report)
        breakdown, missing = _estimate_cost_breakdown(
            usage_by_model,
            _pricing_for_provider(pricing, report.provider),
        )
        breakdowns[str(index)] = breakdown
        missing_models.update(missing)

    return sum_cost_breakdowns(breakdowns), sorted(missing_models)


def _estimate_cost_breakdown(
    usage_by_model: dict[str, TokenUsage],
    catalog: PricingCatalog | None,
) -> tuple[CostBreakdown | None, list[str]]:
    if not usage_by_model:
        return _zero_cost_breakdown(), []
    if catalog is None:
        return None, sorted(usage_by_model)

    breakdowns, missing_models = estimate_by_model_breakdowns(usage_by_model, catalog)
    return sum_cost_breakdowns(breakdowns), missing_models


def _summary_row(
    label: str,
    usage: TokenUsage,
    session_count: int,
    subagent_count: int,
    show_cache_creation: bool,
    include_pricing: bool,
    cost_breakdown: CostBreakdown | None = None,
    provider: str | None = None,
) -> list[str]:
    uncached_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    row: list[str] = []
    if provider is not None:
        row.append(provider)
    row.extend([
        label,
        str(session_count),
        str(subagent_count),
        _format_int(usage.total_tokens),
        _format_int(uncached_input_tokens),
        _format_int(usage.cached_input_tokens),
    ])
    if show_cache_creation:
        row.append(_format_int(usage.cache_creation_tokens))
    row.extend([
        _format_int(usage.output_tokens),
        _format_int(usage.reasoning_output_tokens),
    ])
    if include_pricing:
        row.extend(_format_cost_columns(cost_breakdown, show_cache_creation))
    return row


def _combined_home_row(
    report: Report,
    include_pricing: bool,
    cost_breakdown: CostBreakdown | None,
) -> list[str]:
    row = [
        report.provider,
        report.data_home,
        str(len(report.sessions)),
        _format_int(report.grand_total.input_tokens),
        _format_int(report.grand_total.output_tokens),
    ]
    if include_pricing:
        row.append(_format_usd(_total_cost(cost_breakdown)))
    return row


def _combined_model_rows(
    reports: list[Report],
    pricing: PricingInput,
) -> list[list[str]]:
    models: dict[tuple[str, str], dict[str, Any]] = {}

    for report in reports:
        for model, usage in report.grand_total_by_model.items():
            key = (report.provider, model)
            if key not in models:
                models[key] = {
                    "provider": report.provider,
                    "model": model,
                    "usage": TokenUsage(),
                    "sessions": 0,
                }
            models[key]["usage"] += usage

        for session in report.sessions:
            for model in session.usage_by_model:
                key = (report.provider, model)
                if key not in models:
                    models[key] = {
                        "provider": report.provider,
                        "model": model,
                        "usage": TokenUsage(),
                        "sessions": 0,
                    }
                models[key]["sessions"] += 1

    rows: list[list[str]] = []
    for item in sorted(
        models.values(),
        key=lambda value: (-value["usage"].total_tokens, value["provider"], value["model"]),
    ):
        breakdown, _ = _estimate_cost_breakdown(
            {item["model"]: item["usage"]},
            _pricing_for_provider(pricing, item["provider"]),
        )
        row = [
            item["provider"],
            item["model"],
            str(item["sessions"]),
            _format_int(item["usage"].input_tokens),
            _format_int(item["usage"].output_tokens),
        ]
        if _has_any_pricing(pricing):
            row.append(_format_usd(_total_cost(breakdown)))
        rows.append(row)
    return rows


def _combined_month_row(
    month: str,
    monthly_report: MonthlyReport,
    include_pricing: bool,
    cost_breakdown: CostBreakdown | None,
) -> list[str]:
    row = [
        month,
        str(monthly_report.session_count),
        _format_int(monthly_report.total.input_tokens),
        _format_int(monthly_report.total.output_tokens),
    ]
    if include_pricing:
        row.append(_format_usd(_total_cost(cost_breakdown)))
    return row


def _monthly_summary_section(
    rows: list[list[str]],
    include_pricing: bool,
    show_cache_creation: bool,
) -> list[str]:
    return [
        "",
        "## Monthly Summary",
        "",
        *_render_table(
            headers=_summary_headers("Month", include_pricing, show_cache_creation),
            rows=rows,
            right_align=_summary_right_align(include_pricing, show_cache_creation),
        ),
    ]


def _combined_monthly_summary_section(
    rows: list[list[str]],
    include_pricing: bool,
) -> list[str]:
    headers = ["Month", "Sessions", "Input", "Output"]
    if include_pricing:
        headers.append("Total USD")
    right_align = {1, 2, 3}
    if include_pricing:
        right_align.add(4)
    return [
        "",
        "## Monthly Summary",
        "",
        *_render_table(
            headers=headers,
            rows=rows,
            right_align=right_align,
        ),
    ]


def _summary_headers(
    first_column: str,
    include_pricing: bool,
    show_cache_creation: bool,
    include_provider: bool = False,
) -> list[str]:
    headers: list[str] = []
    if include_provider:
        headers.append("Provider")
    headers.extend([
        first_column,
        "Sessions",
        "Subagents",
        "Total Tokens",
        "Uncached Input",
        "Cached Input",
    ])
    if show_cache_creation:
        headers.append("Cache Creation")
    headers.extend(["Output", "Reasoning"])
    if include_pricing:
        headers.extend(_cost_headers(show_cache_creation))
    return headers


def _summary_right_align(
    include_pricing: bool,
    show_cache_creation: bool,
    include_provider: bool = False,
) -> set[int]:
    text_columns = 2 if include_provider else 1
    right_align = set(range(text_columns, text_columns + 7 + (1 if show_cache_creation else 0)))
    if include_pricing:
        start = text_columns + 7 + (1 if show_cache_creation else 0)
        right_align.update(range(start, start + len(_cost_headers(show_cache_creation))))
    return right_align


def _combined_home_headers(include_pricing: bool) -> list[str]:
    headers = ["Provider", "Home", "Sessions", "Input", "Output"]
    if include_pricing:
        headers.append("Total USD")
    return headers


def _combined_home_right_align(include_pricing: bool) -> set[int]:
    right_align = {2, 3, 4}
    if include_pricing:
        right_align.add(5)
    return right_align


def _combined_model_headers(include_pricing: bool) -> list[str]:
    headers = ["Provider", "Model", "Sessions", "Input", "Output"]
    if include_pricing:
        headers.append("Total USD")
    return headers


def _combined_model_right_align(include_pricing: bool) -> set[int]:
    right_align = {2, 3, 4}
    if include_pricing:
        right_align.add(5)
    return right_align


def _monthly_breakdown_to_markdown(
    month: str,
    monthly_report: MonthlyReport,
    pricing: PricingCatalog | None,
    show_cache_creation: bool = False,
) -> list[str]:
    lines = [
        "",
        f"## {month}",
        "",
        f"- Sessions: `{monthly_report.session_count}`",
        f"- Subagents: `{monthly_report.subagent_count}`",
        f"- Total tokens: `{_format_int(monthly_report.total.total_tokens)}`",
    ]

    monthly_costs: dict[str, float | None] = {}
    monthly_breakdowns: dict[str, CostBreakdown | None] = {}
    missing_models: list[str] = []
    if pricing is not None:
        monthly_breakdowns, missing_models = estimate_by_model_breakdowns(monthly_report.by_model, pricing)
        monthly_costs, missing_models = estimate_by_model_costs(monthly_report.by_model, pricing)
        lines.append(f"- Estimated cost: `{_format_usd(sum_costs(monthly_costs))}`")

    if not monthly_report.by_model:
        lines.extend([
            "",
            "_No model usage recorded._",
        ])
        return lines

    model_rows: list[list[str]] = []
    for model, usage in sorted(
        monthly_report.by_model.items(),
        key=lambda item: item[1].total_tokens,
        reverse=True,
    ):
        uncached_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
        row = [
            model,
            _format_int(usage.total_tokens),
            _format_int(uncached_input_tokens),
            _format_int(usage.cached_input_tokens),
        ]
        if show_cache_creation:
            row.append(_format_int(usage.cache_creation_tokens))
        row.extend([
            _format_int(usage.output_tokens),
            _format_int(usage.reasoning_output_tokens),
        ])
        if pricing is not None:
            row.extend(_format_cost_columns(monthly_breakdowns.get(model), show_cache_creation))
        model_rows.append(row)

    headers = ["Model", "Total Tokens", "Uncached Input", "Cached Input"]
    if show_cache_creation:
        headers.append("Cache Creation")
    headers.extend(["Output", "Reasoning"])
    col_count = len(headers)
    right_align = set(range(1, col_count))
    if pricing is not None:
        headers.extend(_cost_headers(show_cache_creation))
        right_align.update(range(col_count, col_count + len(_cost_headers(show_cache_creation))))

    lines.extend([
        "",
        *_render_table(
            headers=headers,
            rows=model_rows,
            right_align=right_align,
        ),
    ])

    if missing_models:
        lines.extend([
            "",
            f"- Unpriced models: {_format_code_list(missing_models)}",
        ])

    return lines


def _pricing_for_provider(
    pricing: PricingInput,
    provider: str,
) -> PricingCatalog | None:
    if isinstance(pricing, dict):
        return pricing.get(provider)
    return pricing


def _has_any_pricing(pricing: PricingInput) -> bool:
    if isinstance(pricing, dict):
        return bool(pricing)
    return pricing is not None


def _has_cache_creation(usage_by_model: dict[str, TokenUsage]) -> bool:
    for usage in usage_by_model.values():
        if usage.cache_creation_tokens > 0:
            return True
    return False


def _cost_headers(show_cache_creation: bool) -> list[str]:
    headers = ["Input USD", "Cached USD"]
    if show_cache_creation:
        headers.append("Cache Cr. USD")
    headers.extend(["Output USD", "Total USD"])
    return headers


def _sum_tool_tokens(usage_by_model: dict[str, TokenUsage]) -> int:
    return sum(usage.tool_tokens for usage in usage_by_model.values())


def _single_report_title(provider: str) -> str:
    return {
        "claude": "# Claude Code Usage Report",
        "gemini": "# Gemini CLI Usage Report",
    }.get(provider, "# Codex Usage Report")


def _single_home_label(provider: str) -> str:
    return {
        "claude": "CLAUDE_HOME",
        "gemini": "GEMINI_HOME",
    }.get(provider, "CODEX_HOME")




def _zero_cost_breakdown() -> CostBreakdown:
    return CostBreakdown(
        uncached_input_cost=0.0,
        cached_input_cost=0.0,
        output_cost=0.0,
        total_cost=0.0,
        cache_creation_cost=0.0,
    )


def _format_int(value: int) -> str:
    return f"{value:,}"


def _format_usd(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _format_code_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items)


def _format_cost_columns(
    breakdown: CostBreakdown | None,
    show_cache_creation: bool = False,
) -> list[str]:
    if breakdown is None:
        cols = ["N/A", "N/A"]
        if show_cache_creation:
            cols.append("N/A")
        cols.extend(["N/A", "N/A"])
        return cols

    cols = [
        _format_usd(breakdown.uncached_input_cost),
        _format_usd(breakdown.cached_input_cost),
    ]
    if show_cache_creation:
        cols.append(_format_usd(breakdown.cache_creation_cost))
    cols.extend([
        _format_usd(breakdown.output_cost),
        _format_usd(breakdown.total_cost),
    ])
    return cols


def _total_cost(breakdown: CostBreakdown | None) -> float | None:
    if breakdown is None:
        return None
    return breakdown.total_cost


def _render_table(
    headers: list[str],
    rows: list[list[str]],
    right_align: set[int] | None = None,
) -> list[str]:
    right_align = right_align or set()
    widths = [
        max([len(headers[index]), *(len(row[index]) for row in rows)])
        for index in range(len(headers))
    ]

    rendered = [
        _render_table_row(headers, widths, right_align),
        _render_separator(widths, right_align),
    ]
    rendered.extend(_render_table_row(row, widths, right_align) for row in rows)
    return rendered


def _render_table_row(
    row: list[str],
    widths: list[int],
    right_align: set[int],
) -> str:
    cells = []
    for index, cell in enumerate(row):
        if index in right_align:
            cells.append(cell.rjust(widths[index]))
        else:
            cells.append(cell.ljust(widths[index]))
    return "| " + " | ".join(cells) + " |"


def _render_separator(widths: list[int], right_align: set[int]) -> str:
    cells = []
    for index, width in enumerate(widths):
        dash_count = max(3, width)
        if index in right_align:
            cells.append("-" * (dash_count - 1) + ":")
        else:
            cells.append("-" * dash_count)
    return "| " + " | ".join(cells) + " |"
