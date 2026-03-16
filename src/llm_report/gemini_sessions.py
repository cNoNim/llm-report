"""Parse Gemini CLI auto-saved chat sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm_report.models import SessionReport, TokenUsage


def find_all_sessions(gemini_home: Path) -> list[Path]:
    """Discover all Gemini session JSON files under GEMINI_HOME/tmp/*/chats."""
    tmp_dir = gemini_home / "tmp"
    if not tmp_dir.is_dir():
        return []

    return sorted(tmp_dir.glob("*/chats/*.json"))


def parse_session_json(path: Path) -> dict[str, Any]:
    """Read a Gemini session JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_session_report(path: Path, data: dict[str, Any]) -> SessionReport:
    """Build a SessionReport from a Gemini session JSON payload."""
    usage_by_model: dict[str, TokenUsage] = {}

    for message in data.get("messages", []):
        if not isinstance(message, dict) or message.get("type") != "gemini":
            continue

        tokens = message.get("tokens")
        if not isinstance(tokens, dict):
            continue

        model = message.get("model")
        if not isinstance(model, str) or not model:
            model = "unknown"

        usage = TokenUsage(
            input_tokens=_as_int(tokens.get("input")),
            cached_input_tokens=_as_int(tokens.get("cached")),
            output_tokens=_as_int(tokens.get("output")) + _as_int(tokens.get("thoughts")),
            reasoning_output_tokens=_as_int(tokens.get("thoughts")),
            tool_tokens=_as_int(tokens.get("tool")),
            total_tokens=_as_int(tokens.get("total")),
        )

        if model not in usage_by_model:
            usage_by_model[model] = TokenUsage()
        usage_by_model[model] += usage

    total_usage = TokenUsage()
    for usage in usage_by_model.values():
        total_usage += usage

    return SessionReport(
        id=_as_str(data.get("sessionId")) or path.stem,
        title=_extract_title(data.get("messages", [])),
        created_at=_as_str(data.get("startTime")),
        updated_at=_as_str(data.get("lastUpdated")),
        source="cli",
        parent_id=None,
        agent_nickname=None,
        agent_role=None,
        model_provider="google",
        usage_by_model=usage_by_model,
        total_usage=total_usage,
    )


def _extract_title(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""

    for message in messages:
        if not isinstance(message, dict) or message.get("type") != "user":
            continue

        content = message.get("content")
        text = _flatten_content(content)
        if text:
            return text[:120]

    return ""


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = _as_str(item.get("text")).strip()
            else:
                text = ""
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    if isinstance(content, dict):
        return _as_str(content.get("text")).strip()

    return ""


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""
