"""CLI entry point for llm-report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from llm_report.aggregate import combine_reports
from llm_report.claude_collector import claude_collect
from llm_report.config import ConfigLoadError, ReportConfig, find_config_path, load_config
from llm_report.codex_collector import collect
from llm_report.codex_db import StateReadError
from llm_report.codex_utilization import collect_codex_utilization, utilization_to_markdown
from llm_report.gemini_collector import gemini_collect
from llm_report.models import CombinedReport, Report
from llm_report.pricing import PricingCatalog, PricingLoadError, load_default_pricing, load_pricing
from llm_report.report import report_to_json, report_to_markdown


def _resolve_codex_home(args_home: str | None) -> Path:
    """Resolve CODEX_HOME: --home > $CODEX_HOME > ~/.codex."""
    if args_home:
        return Path(args_home).expanduser()
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".codex"


def _resolve_claude_home(args_home: str | None) -> Path:
    """Resolve CLAUDE_HOME: --home > $CLAUDE_HOME > ~/.claude."""
    if args_home:
        return Path(args_home).expanduser()
    env = os.environ.get("CLAUDE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def _resolve_gemini_home(args_home: str | None) -> Path:
    """Resolve GEMINI_HOME: --home > $GEMINI_HOME > ~/.gemini."""
    if args_home:
        return Path(args_home).expanduser()
    env = os.environ.get("GEMINI_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".gemini"


def _detect_provider(args_home: str | None) -> str:
    """Auto-detect provider by checking default paths."""
    codex_home = _resolve_codex_home(args_home)
    claude_home = _resolve_claude_home(args_home)
    gemini_home = _resolve_gemini_home(args_home)
    codex_exists = codex_home.is_dir()
    claude_exists = claude_home.is_dir()
    gemini_exists = gemini_home.is_dir()

    if codex_exists and claude_exists:
        return "codex"
    if codex_exists and gemini_exists:
        return "codex"
    if claude_exists and gemini_exists:
        return "claude"
    if claude_exists:
        return "claude"
    if gemini_exists:
        return "gemini"
    return "codex"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="llm-report",
        description="LLM CLI usage statistics collector",
    )
    sub = parser.add_subparsers(dest="command")

    collect_cmd = sub.add_parser("collect", help="Collect usage statistics as JSON")
    _add_common_arguments(collect_cmd)

    report_cmd = sub.add_parser("report", help="Render a Markdown usage summary")
    _add_common_arguments(report_cmd)
    report_cmd.add_argument(
        "pricing",
        nargs="?",
        metavar="PRICING_JSON",
        help="Optional pricing JSON used to estimate cost in USD",
    )

    utilization_cmd = sub.add_parser("utilization-codex", help="Render Codex utilization summary")
    _add_common_arguments(utilization_cmd)
    utilization_cmd.add_argument(
        "--slot-minutes",
        type=int,
        default=15,
        help="Bucket size in minutes; must divide 1440 (default: 15)",
    )
    utilization_cmd.add_argument(
        "--threshold",
        type=float,
        default=95.0,
        help="Limit used percent treated as constrained (default: 95)",
    )
    utilization_cmd.add_argument(
        "--productive-day-hours",
        type=float,
        default=8.0,
        help="Daily active-hour cap counted as productive (default: 8)",
    )
    utilization_cmd.add_argument(
        "--timezone",
        default="Europe/Moscow",
        help="Timezone used for daily buckets (default: Europe/Moscow)",
    )

    args = parser.parse_args(argv)

    if args.command not in {"collect", "report", "utilization-codex"}:
        parser.print_help()
        sys.exit(1)

    config = _load_config_or_exit(args.config)
    if args.command == "utilization-codex":
        _output_codex_utilization(args, config)
        return

    provider = args.provider
    report = _collect_reports(args, provider, config)
    _output(args, report, config)


def _collect_reports(
    args: argparse.Namespace,
    provider: str,
    config: ReportConfig | None,
) -> Report | CombinedReport:
    reports: list[Report] = []
    codex_homes, claude_homes, gemini_homes = _configured_homes(args, provider, config)

    for home in codex_homes:
        reports.append(_collect_codex_home(home, _account_for_home(config, "codex", home)))

    for home in claude_homes:
        reports.append(_collect_claude_home(home, _account_for_home(config, "claude", home)))

    for home in gemini_homes:
        reports.append(_collect_gemini_home(home, _account_for_home(config, "gemini", home)))

    if args.home:
        if provider == "auto":
            provider = _detect_provider(args.home)
        home = Path(args.home).expanduser()
        if provider == "codex":
            reports.append(_collect_codex_home(home, _account_for_home(config, "codex", home)))
        else:
            reports.append(_collect_single_home(provider, home, config))
    elif not reports:
        if provider == "auto":
            provider = _detect_provider(None)
        reports.append(_collect_default_home(provider, args.home, config))

    if len(reports) == 1:
        return reports[0]
    return combine_reports(reports)


def _collect_single_home(provider: str, home: Path, config: ReportConfig | None) -> Report:
    if provider == "claude":
        return _collect_claude_home(home, _account_for_home(config, "claude", home))
    if provider == "gemini":
        return _collect_gemini_home(home, _account_for_home(config, "gemini", home))
    return _collect_codex_home(home, _account_for_home(config, "codex", home))


def _collect_default_home(provider: str, args_home: str | None, config: ReportConfig | None) -> Report:
    if provider == "claude":
        home = _resolve_claude_home(args_home)
        return _collect_claude_home(home, _account_for_home(config, "claude", home))
    if provider == "gemini":
        home = _resolve_gemini_home(args_home)
        return _collect_gemini_home(home, _account_for_home(config, "gemini", home))
    home = _resolve_codex_home(args_home)
    return _collect_codex_home(home, _account_for_home(config, "codex", home))


def _collect_codex_home(codex_home: Path, account: str | None = None) -> Report:
    if not codex_home.is_dir():
        print(f"Error: CODEX_HOME not found: {codex_home}", file=sys.stderr)
        sys.exit(1)

    try:
        report = collect(codex_home, account=account)
    except StateReadError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    return report


def _collect_claude_home(claude_home: Path, account: str | None = None) -> Report:
    if not claude_home.is_dir():
        print(f"Error: CLAUDE_HOME not found: {claude_home}", file=sys.stderr)
        sys.exit(1)

    return claude_collect(claude_home, account=account)


def _collect_gemini_home(gemini_home: Path, account: str | None = None) -> Report:
    if not gemini_home.is_dir():
        print(f"Error: GEMINI_HOME not found: {gemini_home}", file=sys.stderr)
        sys.exit(1)

    return gemini_collect(gemini_home, account=account)


def _output(
    args: argparse.Namespace,
    report: Report | CombinedReport,
    config: ReportConfig | None,
) -> None:
    if args.command == "collect":
        print(report_to_json(report))
        return

    pricing: PricingCatalog | dict[str, PricingCatalog] | None = None
    if args.pricing:
        try:
            pricing = load_pricing(Path(args.pricing).expanduser())
        except PricingLoadError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        pricing = _load_pricing_for_report(report, config)

    print(report_to_markdown(report, pricing))


def _output_codex_utilization(
    args: argparse.Namespace,
    config: ReportConfig | None,
) -> None:
    homes, _, _ = _configured_homes(args, "codex", config)
    if args.home:
        homes.append(Path(args.home).expanduser())
    elif not homes:
        homes.append(_resolve_codex_home(None))

    for home in homes:
        if not home.is_dir():
            print(f"Error: CODEX_HOME not found: {home}", file=sys.stderr)
            sys.exit(1)

    try:
        report = collect_codex_utilization(
            homes,
            accounts=config.codex_accounts if config is not None else None,
            timezone_name=args.timezone,
            slot_minutes=args.slot_minutes,
            threshold_percent=args.threshold,
            productive_day_hours=args.productive_day_hours,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(utilization_to_markdown(report))


def _account_for_home(config: ReportConfig | None, provider: str, home: Path) -> str | None:
    if config is None:
        return None
    return config.accounts_for_provider(provider).get(home)


def _load_pricing_for_report(
    report: Report | CombinedReport,
    config: ReportConfig | None,
) -> PricingCatalog | dict[str, PricingCatalog] | None:
    if config is not None:
        pricing = _load_config_pricing_for_report(report, config)
        if pricing is not None:
            return pricing

    return _load_default_pricing_for_report(report)


def _load_config_pricing_for_report(
    report: Report | CombinedReport,
    config: ReportConfig,
) -> PricingCatalog | dict[str, PricingCatalog] | None:
    if not config.pricing_paths:
        return None

    try:
        if isinstance(report, CombinedReport):
            catalogs: dict[str, PricingCatalog] = {}
            for provider in sorted({home.provider for home in report.homes}):
                path = config.pricing_paths.get(provider)
                if path is not None:
                    catalogs[provider] = load_pricing(path)
            return catalogs or None

        path = config.pricing_paths.get(report.provider)
        if path is None:
            return None
        return load_pricing(path)
    except PricingLoadError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _load_default_pricing_for_report(
    report: Report | CombinedReport,
) -> PricingCatalog | dict[str, PricingCatalog] | None:
    if isinstance(report, CombinedReport):
        catalogs: dict[str, PricingCatalog] = {}
        for provider in sorted({home.provider for home in report.homes}):
            catalog = load_default_pricing(provider)
            if catalog is not None:
                catalogs[provider] = catalog
        return catalogs or None

    return load_default_pricing(report.provider)


def _load_config_or_exit(config_path: str | None) -> ReportConfig | None:
    resolved_path = Path(config_path).expanduser() if config_path else find_config_path()
    if resolved_path is None:
        return None

    try:
        return load_config(resolved_path)
    except ConfigLoadError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _configured_homes(
    args: argparse.Namespace,
    provider: str,
    config: ReportConfig | None,
) -> tuple[list[Path], list[Path], list[Path]]:
    if args.home or args.codex_home or args.claude_home or args.gemini_home:
        return (
            [Path(home).expanduser() for home in args.codex_home],
            [Path(home).expanduser() for home in args.claude_home],
            [Path(home).expanduser() for home in args.gemini_home],
        )

    if config is None:
        return ([], [], [])

    if provider == "codex":
        return (list(config.codex_homes), [], [])
    if provider == "claude":
        return ([], list(config.claude_homes), [])
    if provider == "gemini":
        return ([], [], list(config.gemini_homes))

    return (
        list(config.codex_homes),
        list(config.claude_homes),
        list(config.gemini_homes),
    )


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to TOML config with home and pricing settings",
    )
    subparser.add_argument(
        "--home",
        metavar="PATH",
        help="Path to data home (default: auto-detected)",
    )
    subparser.add_argument(
        "--codex-home",
        action="append",
        default=[],
        metavar="PATH",
        help="Codex data home; repeat to include multiple CODEX_HOME paths",
    )
    subparser.add_argument(
        "--claude-home",
        action="append",
        default=[],
        metavar="PATH",
        help="Claude data home; repeat to include multiple CLAUDE_HOME paths",
    )
    subparser.add_argument(
        "--gemini-home",
        action="append",
        default=[],
        metavar="PATH",
        help="Gemini data home; repeat to include multiple GEMINI_HOME paths",
    )
    subparser.add_argument(
        "--provider",
        choices=["codex", "claude", "gemini", "auto"],
        default="auto",
        help="Provider for --home or default auto-detection (default: auto)",
    )
