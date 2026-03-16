"""Tests for the Codex collector module."""

import json
import sqlite3
from pathlib import Path

from llm_report.codex_collector import collect, _parse_source
from llm_report.models import TokenUsage

FIXTURES = Path(__file__).parent / "fixtures"


def _create_test_db(db_path: Path, threads: list[dict]) -> None:
    """Create a minimal state DB with the given thread rows."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            source TEXT NOT NULL,
            model_provider TEXT NOT NULL,
            cwd TEXT NOT NULL,
            title TEXT NOT NULL,
            sandbox_policy TEXT NOT NULL,
            approval_mode TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            has_user_event INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at INTEGER,
            git_sha TEXT,
            git_branch TEXT,
            git_origin_url TEXT,
            agent_nickname TEXT,
            agent_role TEXT
        )
    """)
    for t in threads:
        conn.execute(
            """
            INSERT INTO threads (id, rollout_path, created_at, updated_at, source,
                                 model_provider, cwd, title, sandbox_policy, approval_mode,
                                 tokens_used, agent_nickname, agent_role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t["id"], t["rollout_path"], t["created_at"], t["updated_at"],
                t["source"], t["model_provider"], t["cwd"], t["title"],
                t["sandbox_policy"], t["approval_mode"], t["tokens_used"],
                t.get("agent_nickname"), t.get("agent_role"),
            ),
        )
    conn.commit()
    conn.close()


def test_collect_with_rollout(tmp_path):
    """Collect should parse rollout and produce correct per-model usage."""
    rollout_path = FIXTURES / "sample.jsonl"

    _create_test_db(tmp_path / "state_5.sqlite", [{
        "id": "019d0000-0000-0000-0000-000000000001",
        "rollout_path": str(rollout_path),
        "created_at": 1773928800,  # 2026-03-16T10:00:00Z
        "updated_at": 1773928860,
        "source": "cli",
        "model_provider": "openai",
        "cwd": "/tmp/test",
        "title": "Test session",
        "sandbox_policy": "read_only",
        "approval_mode": "on_failure",
        "tokens_used": 6600,
    }])

    report = collect(tmp_path)

    assert len(report.sessions) == 1
    s = report.sessions[0]
    assert s.source == "cli"
    assert s.parent_id is None
    assert set(s.usage_by_model.keys()) == {"gpt-5.4", "o3"}
    assert s.total_usage.total_tokens == 6600

    assert "2026-03" in report.monthly
    mr = report.monthly["2026-03"]
    assert mr.session_count == 1
    assert mr.subagent_count == 0
    assert mr.total.total_tokens == 6600

    assert report.grand_total.total_tokens == 6600


def test_collect_fallback_to_db_tokens(tmp_path):
    """When rollout has no token_count events, fall back to DB tokens_used."""
    rollout = tmp_path / "sessions" / "rollout.jsonl"
    rollout.parent.mkdir(parents=True)
    # Rollout with only turn_context, no token_count
    rollout.write_text(
        '{"timestamp":"T","type":"turn_context","payload":{"cwd":"/tmp","model":"gpt-5.4","approval_policy":"on_failure","sandbox_policy":{"type":"read_only"},"summary":"auto"}}\n'
    )

    _create_test_db(tmp_path / "state_5.sqlite", [{
        "id": "019d0000-0000-0000-0000-000000000002",
        "rollout_path": str(rollout),
        "created_at": 1773928800,
        "updated_at": 1773928860,
        "source": "cli",
        "model_provider": "openai",
        "cwd": "/tmp",
        "title": "Fallback session",
        "sandbox_policy": "read_only",
        "approval_mode": "on_failure",
        "tokens_used": 5000,
    }])

    report = collect(tmp_path)
    s = report.sessions[0]
    assert s.usage_by_model == {"gpt-5.4": TokenUsage(total_tokens=5000)}


def test_collect_missing_rollout(tmp_path):
    """When rollout file doesn't exist, attribute tokens to 'unknown'."""
    _create_test_db(tmp_path / "state_5.sqlite", [{
        "id": "019d0000-0000-0000-0000-000000000003",
        "rollout_path": "/nonexistent/rollout.jsonl",
        "created_at": 1773928800,
        "updated_at": 1773928860,
        "source": "cli",
        "model_provider": "openai",
        "cwd": "/tmp",
        "title": "Missing rollout",
        "sandbox_policy": "read_only",
        "approval_mode": "on_failure",
        "tokens_used": 1000,
    }])

    report = collect(tmp_path)
    s = report.sessions[0]
    assert s.usage_by_model == {"unknown": TokenUsage(total_tokens=1000)}


def test_collect_no_db(tmp_path):
    """When no state DB exists, return empty report."""
    report = collect(tmp_path)
    assert report.sessions == []
    assert report.monthly == {}


def test_parse_source_simple():
    assert _parse_source("cli") == ("cli", None)
    assert _parse_source("vscode") == ("vscode", None)
    assert _parse_source("exec") == ("exec", None)
    assert _parse_source("mcp") == ("mcp", None)


def test_parse_source_subagent():
    raw = json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": "abc-123", "depth": 1}}})
    source, parent_id = _parse_source(raw)
    assert source == "subagent"
    assert parent_id == "abc-123"


def test_parse_source_subagent_no_parent():
    raw = json.dumps({"subagent": "review"})
    source, parent_id = _parse_source(raw)
    assert source == "subagent"
    assert parent_id is None


def test_monthly_aggregation(tmp_path):
    """Multiple sessions in the same month should aggregate correctly."""
    rollout1 = tmp_path / "r1.jsonl"
    rollout2 = tmp_path / "r2.jsonl"
    rollout1.write_text("")
    rollout2.write_text("")

    _create_test_db(tmp_path / "state_5.sqlite", [
        {
            "id": "019d0000-0000-0000-0000-000000000010",
            "rollout_path": str(rollout1),
            "created_at": 1773928800,
            "updated_at": 1773928860,
            "source": "cli",
            "model_provider": "openai",
            "cwd": "/tmp",
            "title": "Session 1",
            "sandbox_policy": "read_only",
            "approval_mode": "on_failure",
            "tokens_used": 100,
        },
        {
            "id": "019d0000-0000-0000-0000-000000000011",
            "rollout_path": str(rollout2),
            "created_at": 1773932400,  # same day, 1 hour later
            "updated_at": 1773932460,
            "source": json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": "p1", "depth": 1}}}),
            "model_provider": "openai",
            "cwd": "/tmp",
            "title": "Subagent",
            "sandbox_policy": "read_only",
            "approval_mode": "on_failure",
            "tokens_used": 200,
        },
    ])

    report = collect(tmp_path)
    assert len(report.sessions) == 2
    mr = report.monthly["2026-03"]
    assert mr.session_count == 2
    assert mr.subagent_count == 1
    assert mr.total.total_tokens == 300
    assert sorted(mr.daily.keys()) == ["2026-03-19"]
    dr = mr.daily["2026-03-19"]
    assert dr.session_count == 2
    assert dr.subagent_count == 1
    assert dr.total.total_tokens == 300
    assert report.grand_total.total_tokens == 300


def test_daily_aggregation_splits_days_within_month(tmp_path):
    rollout1 = tmp_path / "r1.jsonl"
    rollout2 = tmp_path / "r2.jsonl"
    rollout1.write_text("")
    rollout2.write_text("")

    _create_test_db(tmp_path / "state_5.sqlite", [
        {
            "id": "019d0000-0000-0000-0000-000000000020",
            "rollout_path": str(rollout1),
            "created_at": 1773928800,  # 2026-03-19T10:00:00Z
            "updated_at": 1773928860,
            "source": "cli",
            "model_provider": "openai",
            "cwd": "/tmp",
            "title": "Day 1",
            "sandbox_policy": "read_only",
            "approval_mode": "on_failure",
            "tokens_used": 100,
        },
        {
            "id": "019d0000-0000-0000-0000-000000000021",
            "rollout_path": str(rollout2),
            "created_at": 1774015200,  # 2026-03-20T10:00:00Z
            "updated_at": 1774015260,
            "source": "cli",
            "model_provider": "openai",
            "cwd": "/tmp",
            "title": "Day 2",
            "sandbox_policy": "read_only",
            "approval_mode": "on_failure",
            "tokens_used": 200,
        },
    ])

    report = collect(tmp_path)
    mr = report.monthly["2026-03"]
    assert sorted(mr.daily.keys()) == ["2026-03-19", "2026-03-20"]
    assert mr.daily["2026-03-19"].total.total_tokens == 100
    assert mr.daily["2026-03-19"].session_count == 1
    assert mr.daily["2026-03-20"].total.total_tokens == 200
    assert mr.daily["2026-03-20"].session_count == 1
