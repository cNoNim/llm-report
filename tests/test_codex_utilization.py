"""Tests for Codex utilization buckets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from llm_report.codex_utilization import collect_codex_utilization, utilization_to_markdown


def test_collect_codex_utilization_paints_active_and_constrained_slots(tmp_path):
    home = tmp_path / "codex"
    rollout = home / "sessions" / "2026" / "05" / "01" / "rollout.jsonl"
    _write_rollout(
        rollout,
        [{
            "timestamp": "2026-05-01T09:02:00Z",
            "primary": {
                "used_percent": 95.0,
                "window_minutes": 300,
                "resets_at": _epoch("2026-05-01T10:00:00Z"),
            },
            "secondary": {
                "used_percent": 10.0,
                "window_minutes": 10080,
                "resets_at": _epoch("2026-05-08T10:00:00Z"),
            },
        }],
    )

    report = collect_codex_utilization([home], timezone_name="Europe/Moscow")
    summary = report.monthly_by_account["unknown"]["2026-05"]

    assert summary.days == 1
    assert summary.active_slots == 1
    assert summary.productive_slots == 1
    assert summary.overhead_slots == 0
    assert summary.constrained_5h_slots == 4
    assert summary.constrained_weekly_slots == 0
    assert summary.near_5h_days == 1
    assert summary.near_weekly_days == 0


def test_collect_codex_utilization_merges_parallel_homes(tmp_path):
    home_a = tmp_path / "codex-a"
    home_b = tmp_path / "codex-b"
    _write_rollout(
        home_a / "sessions" / "rollout-a.jsonl",
        [{"timestamp": "2026-05-01T09:02:00Z"}],
    )
    _write_rollout(
        home_b / "sessions" / "rollout-b.jsonl",
        [{"timestamp": "2026-05-01T09:10:00Z"}],
    )

    report = collect_codex_utilization(
        [home_a, home_b],
        accounts={
            home_a: "account-a",
            home_b: "account-b",
        },
        timezone_name="UTC",
    )

    assert report.monthly_by_account["account-a"]["2026-05"].active_slots == 1
    assert report.monthly_by_account["account-b"]["2026-05"].active_slots == 1
    assert report.monthly_by_home[str(home_a)]["2026-05"].active_slots == 1
    assert report.monthly_by_home[str(home_b)]["2026-05"].active_slots == 1


def test_utilization_to_markdown_renders_monthly_summary(tmp_path):
    home = tmp_path / "codex"
    _write_rollout(
        home / "sessions" / "rollout.jsonl",
        [{"timestamp": "2026-05-01T09:02:00Z"}],
    )

    report = collect_codex_utilization([home], timezone_name="UTC")
    markdown = utilization_to_markdown(report)

    assert "# Codex Utilization Report" in markdown
    assert "## Account: unknown" in markdown
    assert "### Monthly Summary" in markdown
    assert "| 2026-05 |" in markdown
    assert "### Home Breakdown" not in markdown
    assert str(home) not in markdown


def _write_rollout(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for event in events:
        primary = event.get("primary")
        secondary = event.get("secondary")
        lines.append(json.dumps({
            "timestamp": event["timestamp"],
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"total_tokens": 1},
                    "last_token_usage": {"total_tokens": 1},
                },
                "rate_limits": {
                    "primary": primary,
                    "secondary": secondary,
                    "rate_limit_reached_type": None,
                },
            },
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
