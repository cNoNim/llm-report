"""Tests for gemini_collector module."""

from pathlib import Path

from llm_report.gemini_collector import gemini_collect

FIXTURES = Path(__file__).parent / "fixtures"


def test_gemini_collect_with_sessions(tmp_path):
    chats_dir = tmp_path / "tmp" / "project-a" / "chats"
    chats_dir.mkdir(parents=True)
    (chats_dir / "session-a.json").write_text((FIXTURES / "gemini_session.json").read_text())

    report = gemini_collect(tmp_path)

    assert report.provider == "gemini"
    assert report.data_home == str(tmp_path)
    assert len(report.sessions) == 1
    assert report.sessions[0].model_provider == "google"
    assert "2026-03" in report.monthly
    assert report.monthly["2026-03"].session_count == 1
    assert report.monthly["2026-03"].daily["2026-03-16"].session_count == 1
    assert report.grand_total.total_tokens == 1760
    assert report.grand_total.tool_tokens == 20
    assert "gemini-2.5-pro" in report.grand_total_by_model
    assert "gemini-2.5-flash" in report.grand_total_by_model


def test_gemini_collect_empty(tmp_path):
    report = gemini_collect(tmp_path)

    assert report.provider == "gemini"
    assert report.sessions == []
    assert report.monthly == {}
    assert report.grand_total.is_zero()
