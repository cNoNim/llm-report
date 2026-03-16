"""Tests for the CLI entry point."""

import json
import sqlite3
from pathlib import Path

import pytest

from llm_report.cli import main
from llm_report.pricing import PricingCatalog, ModelPricing


def test_main_exits_with_error_for_unreadable_state_db(tmp_path, capsys):
    db_path = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE not_threads (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(SystemExit) as exc:
        main(["collect", "--home", str(tmp_path), "--provider", "codex"])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Failed to read threads" in captured.err


def test_main_report_renders_markdown_for_empty_state(tmp_path, capsys):
    main(["report", "--home", str(tmp_path), "--provider", "codex"])

    captured = capsys.readouterr()
    assert "# Codex Usage Report" in captured.out
    assert "## Monthly Summary" in captured.out


def test_main_report_loads_pricing_json(tmp_path, capsys):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({
        "source_url": "https://developers.openai.com/api/docs/pricing/",
        "unit": "usd_per_1m_tokens",
        "models": {
            "gpt-5.4": {
                "input": 2.5,
                "cached_input": 0.25,
                "output": 15.0,
            },
        },
    }))

    main(["report", "--home", str(tmp_path), "--provider", "codex", str(pricing_path)])

    captured = capsys.readouterr()
    assert "Estimated cost: `$0.00`" in captured.out
    assert "**Pricing Source**" in captured.out
    assert "- `https://developers.openai.com/api/docs/pricing/`" in captured.out


def test_main_claude_report_renders_markdown(tmp_path, capsys):
    # Create minimal Claude structure
    (tmp_path / "stats-cache.json").write_text("{}")
    (tmp_path / "projects").mkdir()

    main(["report", "--home", str(tmp_path), "--provider", "claude"])

    captured = capsys.readouterr()
    assert "# Claude Code Usage Report" in captured.out


def test_main_gemini_report_renders_markdown(tmp_path, capsys):
    (tmp_path / "tmp").mkdir()

    main(["report", "--home", str(tmp_path), "--provider", "gemini"])

    captured = capsys.readouterr()
    assert "# Gemini CLI Usage Report" in captured.out


def test_main_auto_detects_codex(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".codex").mkdir()

    main(["report", "--provider", "auto"])

    captured = capsys.readouterr()
    assert "# Codex Usage Report" in captured.out


def test_main_auto_detects_gemini(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_HOME", raising=False)
    monkeypatch.delenv("GEMINI_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gemini" / "tmp").mkdir(parents=True)

    main(["report", "--provider", "auto"])

    captured = capsys.readouterr()
    assert "# Gemini CLI Usage Report" in captured.out


def test_main_renders_combined_report_for_multiple_homes(tmp_path, capsys):
    codex_home = tmp_path / "codex-a"
    claude_home = tmp_path / "claude-a"
    codex_home.mkdir()
    _create_threads_db(codex_home / "state_5.sqlite")
    (claude_home / "projects").mkdir(parents=True)

    main([
        "report",
        "--codex-home", str(codex_home),
        "--claude-home", str(claude_home),
    ])

    captured = capsys.readouterr()
    assert "# Combined Usage Report" in captured.out
    assert str(codex_home) in captured.out
    assert str(claude_home) in captured.out


def test_main_renders_combined_report_from_config(tmp_path, capsys):
    codex_home = tmp_path / "codex-a"
    claude_home = tmp_path / "claude-a"
    codex_home.mkdir()
    _create_threads_db(codex_home / "state_5.sqlite")
    (claude_home / "projects").mkdir(parents=True)

    config_path = tmp_path / "llm-report.toml"
    config_path.write_text(
        f"""
[homes]
codex = ["{codex_home}"]
claude = ["{claude_home}"]
""".strip(),
        encoding="utf-8",
    )

    main(["report", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert "# Combined Usage Report" in captured.out
    assert str(codex_home) in captured.out
    assert str(claude_home) in captured.out


def test_main_uses_default_config_when_local_config_missing(tmp_path, capsys, monkeypatch):
    codex_home = tmp_path / "codex-a"
    claude_home = tmp_path / "claude-a"
    codex_home.mkdir()
    _create_threads_db(codex_home / "state_5.sqlite")
    (claude_home / "projects").mkdir(parents=True)

    default_config_path = tmp_path / "llm-report.default.toml"
    default_config_path.write_text(
        f"""
[homes]
codex = ["{codex_home}"]
claude = ["{claude_home}"]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    main(["report"])

    captured = capsys.readouterr()
    assert "# Combined Usage Report" in captured.out
    assert str(codex_home) in captured.out
    assert str(claude_home) in captured.out


def test_main_auto_loads_default_pricing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "llm_report.cli.load_default_pricing",
        lambda provider: PricingCatalog(
            source_url=f"https://example.com/{provider}",
            extracted_at=None,
            unit="usd_per_1m_tokens",
            models={"gpt-5.4": ModelPricing(input=2.5, cached_input=0.25, output=15.0)},
        ) if provider == "codex" else None,
    )

    main(["report", "--home", str(tmp_path), "--provider", "codex"])

    captured = capsys.readouterr()
    assert "Estimated cost: `$0.00`" in captured.out
    assert "**Pricing Source**" in captured.out
    assert "- `https://example.com/codex`" in captured.out


def test_main_loads_pricing_from_config(tmp_path, capsys, monkeypatch):
    pricing_path = tmp_path / "pricing.openai.json"
    pricing_path.write_text(json.dumps({
        "source_url": "https://example.com/config-pricing",
        "unit": "usd_per_1m_tokens",
        "models": {
            "gpt-5.4": {
                "input": 2.5,
                "cached_input": 0.25,
                "output": 15.0,
            },
        },
    }), encoding="utf-8")

    config_path = tmp_path / "llm-report.toml"
    config_path.write_text(
        """
[pricing]
codex = "pricing.openai.json"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr("llm_report.cli.load_default_pricing", lambda provider: None)

    main(["report", "--home", str(tmp_path), "--provider", "codex", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert "Estimated cost: `$0.00`" in captured.out
    assert "- `https://example.com/config-pricing`" in captured.out


def _create_threads_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()
