"""Tests for claude_sessions module."""

import json
from pathlib import Path

from llm_report.claude_sessions import (
    build_session_report,
    find_all_sessions,
    parse_session_jsonl,
)
from llm_report.models import TokenUsage

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_session_jsonl():
    usage = parse_session_jsonl(FIXTURES / "claude_session.jsonl")

    assert "claude-sonnet-4-6" in usage
    assert "claude-opus-4-6" in usage

    sonnet = usage["claude-sonnet-4-6"]
    # Two assistant messages: (10+500+100+15+600+50) = 1275 input, (500+600) = 1100 cached
    assert sonnet.input_tokens == 1275
    assert sonnet.cached_input_tokens == 1100
    assert sonnet.cache_creation_5m_tokens == 90   # 40 + 50
    assert sonnet.cache_creation_1h_tokens == 60   # 60 + 0
    assert sonnet.cache_creation_tokens == 150
    assert sonnet.output_tokens == 50
    assert sonnet.total_tokens == 1325  # 10+500+100+20 + 15+600+50+30

    opus = usage["claude-opus-4-6"]
    assert opus.input_tokens == 285  # 5+200+80
    assert opus.cached_input_tokens == 200
    assert opus.cache_creation_5m_tokens == 0
    assert opus.cache_creation_1h_tokens == 80
    assert opus.cache_creation_tokens == 80
    assert opus.output_tokens == 10
    assert opus.total_tokens == 295  # 5+200+80+10


def test_parse_session_jsonl_missing_file(tmp_path):
    usage = parse_session_jsonl(tmp_path / "nonexistent.jsonl")
    assert usage == {}


def test_parse_session_jsonl_empty_file(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    usage = parse_session_jsonl(p)
    assert usage == {}


def test_find_all_sessions(tmp_path):
    proj = tmp_path / "projects" / "test-project"
    proj.mkdir(parents=True)
    index = {
        "version": 1,
        "entries": [
            {
                "sessionId": "abc-123",
                "summary": "Test session",
                "created": "2026-03-10T10:00:00Z",
                "modified": "2026-03-10T10:30:00Z",
                "isSidechain": False,
                "fullPath": "/tmp/fake.jsonl",
            },
            {
                "sessionId": "def-456",
                "summary": "Sub session",
                "created": "2026-03-10T11:00:00Z",
                "modified": "2026-03-10T11:30:00Z",
                "isSidechain": True,
                "fullPath": "/tmp/fake2.jsonl",
            },
        ],
    }
    (proj / "sessions-index.json").write_text(json.dumps(index))

    entries = find_all_sessions(tmp_path)
    assert len(entries) == 2
    assert entries[0]["sessionId"] == "abc-123"
    assert entries[1]["sessionId"] == "def-456"
    assert entries[0]["_project_dir"] == str(proj)


def test_find_all_sessions_no_projects(tmp_path):
    entries = find_all_sessions(tmp_path)
    assert entries == []


def test_build_session_report():
    entry = {
        "sessionId": "abc-123",
        "summary": "Test session",
        "created": "2026-03-10T10:00:00Z",
        "modified": "2026-03-10T10:30:00Z",
        "isSidechain": False,
    }
    usage = {
        "claude-sonnet-4-6": TokenUsage(
            input_tokens=100, output_tokens=50, total_tokens=150,
        ),
    }

    session = build_session_report(entry, usage)

    assert session.id == "abc-123"
    assert session.title == "Test session"
    assert session.source == "cli"
    assert session.model_provider == "anthropic"
    assert session.total_usage.total_tokens == 150


def test_build_session_report_sidechain():
    entry = {
        "sessionId": "def-456",
        "summary": "Sub session",
        "created": "2026-03-10T11:00:00Z",
        "modified": "2026-03-10T11:30:00Z",
        "isSidechain": True,
    }

    session = build_session_report(entry, {})
    assert session.source == "subagent"
    assert session.total_usage.is_zero()
