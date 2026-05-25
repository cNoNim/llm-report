from pathlib import Path

import pytest

from llm_report.config import ConfigLoadError, find_config_path, load_config


def test_load_config_resolves_relative_paths(tmp_path):
    config_path = tmp_path / "llm-report.toml"
    config_path.write_text(
        """
[homes]
codex = ["./data/codex", "~/.codex"]
claude = ["./data/claude"]

[pricing]
codex = "pricing/pricing.openai.json"

[accounts.codex]
"./data/codex" = "personal"
"~/.codex" = "default"

[accounts.claude]
"./data/claude" = "work"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.codex_homes[0] == tmp_path / "data" / "codex"
    assert config.codex_homes[1] == Path("~/.codex").expanduser()
    assert config.claude_homes == (tmp_path / "data" / "claude",)
    assert config.gemini_homes == ()
    assert config.pricing_paths["codex"] == tmp_path / "pricing" / "pricing.openai.json"
    assert config.codex_accounts[tmp_path / "data" / "codex"] == "personal"
    assert config.codex_accounts[Path("~/.codex").expanduser()] == "default"
    assert config.accounts_for_provider("claude")[tmp_path / "data" / "claude"] == "work"
    assert config.accounts_for_provider("gemini") == {}


def test_load_config_rejects_invalid_home_list(tmp_path):
    config_path = tmp_path / "llm-report.toml"
    config_path.write_text(
        """
[homes]
codex = "not-a-list"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError):
        load_config(config_path)


def test_find_config_path_prefers_local_then_default(tmp_path):
    default_path = tmp_path / "llm-report.default.toml"
    default_path.write_text("", encoding="utf-8")

    assert find_config_path(tmp_path) == default_path

    local_path = tmp_path / "llm-report.toml"
    local_path.write_text("", encoding="utf-8")

    assert find_config_path(tmp_path) == local_path
