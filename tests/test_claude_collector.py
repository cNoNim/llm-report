"""Tests for claude_collector module."""

import json
from pathlib import Path

from llm_report.claude_collector import claude_collect

FIXTURES = Path(__file__).parent / "fixtures"


def test_claude_collect_with_sessions(tmp_path):
    """Full integration: JSONL files discovered from project directory."""
    proj = tmp_path / "projects" / "test-project"
    proj.mkdir(parents=True)

    session_id = "abc-123"
    jsonl_path = proj / f"{session_id}.jsonl"
    jsonl_path.write_text((FIXTURES / "claude_session.jsonl").read_text())

    report = claude_collect(tmp_path)

    assert report.provider == "claude"
    assert report.data_home == str(tmp_path)
    assert len(report.sessions) == 1
    assert report.sessions[0].id == session_id
    assert report.sessions[0].model_provider == "anthropic"

    # Check monthly aggregation
    assert "2026-03" in report.monthly
    mr = report.monthly["2026-03"]
    assert mr.session_count == 1
    assert mr.total.total_tokens > 0

    # Check grand total
    assert report.grand_total.total_tokens > 0
    assert "claude-sonnet-4-6" in report.grand_total_by_model
    assert "claude-opus-4-6" in report.grand_total_by_model


def test_claude_collect_empty(tmp_path):
    """When nothing exists, return empty report."""
    report = claude_collect(tmp_path)

    assert report.provider == "claude"
    assert report.sessions == []
    assert report.monthly == {}
    assert report.grand_total.is_zero()


def test_claude_collect_session_without_jsonl(tmp_path):
    """Session in index but JSONL file missing — session with empty usage."""
    proj = tmp_path / "projects" / "test-project"
    proj.mkdir(parents=True)

    index = {
        "version": 1,
        "entries": [
            {
                "sessionId": "missing-jsonl",
                "summary": "Missing JSONL",
                "created": "2026-03-10T10:00:00Z",
                "modified": "2026-03-10T10:30:00Z",
                "isSidechain": False,
                "fullPath": "/nonexistent/path.jsonl",
            },
        ],
    }
    (proj / "sessions-index.json").write_text(json.dumps(index))

    report = claude_collect(tmp_path)

    assert len(report.sessions) == 1
    assert report.sessions[0].total_usage.is_zero()
