"""Tests for Gemini session parsing."""

import json
from pathlib import Path

from llm_report.gemini_sessions import build_session_report, find_all_sessions, parse_session_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_find_all_sessions_discovers_chat_json_files(tmp_path):
    chats_dir = tmp_path / "tmp" / "project-a" / "chats"
    chats_dir.mkdir(parents=True)
    (chats_dir / "session-a.json").write_text("{}")
    (chats_dir / "session-b.json").write_text("{}")

    paths = find_all_sessions(tmp_path)

    assert [path.name for path in paths] == ["session-a.json", "session-b.json"]


def test_parse_session_json_reads_valid_payload():
    path = FIXTURES / "gemini_session.json"

    payload = parse_session_json(path)

    assert payload["sessionId"] == "session-2026-03-16T09-15-sample"


def test_build_session_report_maps_usage_and_title():
    path = FIXTURES / "gemini_session.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    session = build_session_report(path, payload)

    assert session.id == "session-2026-03-16T09-15-sample"
    assert session.title == "inspect the repo and summarize the architecture"
    assert session.created_at == "2026-03-16T09:15:00.000Z"
    assert session.updated_at == "2026-03-16T09:17:00.000Z"
    assert session.model_provider == "google"
    assert session.usage_by_model["gemini-2.5-pro"].input_tokens == 1000
    assert session.usage_by_model["gemini-2.5-pro"].cached_input_tokens == 400
    assert session.usage_by_model["gemini-2.5-pro"].output_tokens == 180
    assert session.usage_by_model["gemini-2.5-pro"].reasoning_output_tokens == 30
    assert session.usage_by_model["gemini-2.5-pro"].tool_tokens == 20
    assert session.usage_by_model["gemini-2.5-pro"].total_tokens == 1200
    assert session.total_usage.input_tokens == 1500
    assert session.total_usage.cached_input_tokens == 500
    assert session.total_usage.output_tokens == 240
    assert session.total_usage.reasoning_output_tokens == 40
    assert session.total_usage.tool_tokens == 20
    assert session.total_usage.total_tokens == 1760
