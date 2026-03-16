"""Parse Claude Code sessions and sessions-index.json."""

from __future__ import annotations

import json
from pathlib import Path

from llm_report.models import SessionReport, TokenUsage


def find_all_sessions(claude_home: Path) -> list[dict]:
    """Collect all session entries by scanning project directories.

    Two discovery strategies, merged and deduplicated by sessionId:
    1. sessions-index.json entries (may have stale fullPath)
    2. Bare *.jsonl files in project directories (primary source)
    """
    projects_dir = claude_home / "projects"
    if not projects_dir.is_dir():
        return []

    seen_ids: set[str] = set()
    entries: list[dict] = []

    # Strategy 1: scan bare JSONL files (these are the actual session files)
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_path in project_dir.glob("*.jsonl"):
            session_id = jsonl_path.stem
            if session_id in seen_ids:
                continue
            seen_ids.add(session_id)
            entry = _entry_from_jsonl(jsonl_path, session_id)
            entry["_project_dir"] = str(project_dir)
            entries.append(entry)

    # Strategy 2: sessions-index.json (for sessions whose JSONL was cleaned up)
    for index_path in projects_dir.glob("*/sessions-index.json"):
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(data, dict):
            continue

        for entry in data.get("entries", []):
            if not isinstance(entry, dict):
                continue
            sid = entry.get("sessionId")
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            entry["_project_dir"] = str(index_path.parent)
            entries.append(entry)

    return entries


def _entry_from_jsonl(path: Path, session_id: str) -> dict:
    """Extract session metadata from a JSONL file by reading first/last lines."""
    entry: dict = {
        "sessionId": session_id,
        "fullPath": str(path),
        "isSidechain": False,
    }

    try:
        with path.open(encoding="utf-8") as f:
            first_ts = None
            last_ts = None
            summary = None

            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp")
                if ts and first_ts is None:
                    first_ts = ts
                if ts:
                    last_ts = ts

                if obj.get("isSidechain"):
                    entry["isSidechain"] = True

                # Use first user message as title
                if summary is None and obj.get("type") == "user":
                    msg = obj.get("message", {})
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if isinstance(content, str) and content:
                            summary = content[:120]

            if first_ts:
                entry["created"] = first_ts
            if last_ts:
                entry["modified"] = last_ts
            if summary:
                entry["firstPrompt"] = summary

    except OSError:
        pass

    return entry


def parse_session_jsonl(path: Path) -> dict[str, TokenUsage]:
    """Parse a session JSONL file, summing usage from assistant messages by model."""
    usage_by_model: dict[str, TokenUsage] = {}

    if not path.exists():
        return usage_by_model

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return usage_by_model

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("type") != "assistant":
            continue

        message = obj.get("message", {})
        if not isinstance(message, dict):
            continue

        model = message.get("model", "unknown")
        if model.startswith("<"):
            continue
        usage = message.get("usage", {})
        if not isinstance(usage, dict):
            continue

        input_tokens = usage.get("input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation_total = usage.get("cache_creation_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        cc = usage.get("cache_creation", {})
        if isinstance(cc, dict):
            cc_5m = cc.get("ephemeral_5m_input_tokens", 0)
            cc_1h = cc.get("ephemeral_1h_input_tokens", 0)
        else:
            cc_5m = cache_creation_total
            cc_1h = 0

        total = input_tokens + cache_read + cache_creation_total + output_tokens

        tu = TokenUsage(
            input_tokens=input_tokens + cache_read + cache_creation_total,
            cached_input_tokens=cache_read,
            cache_creation_5m_tokens=cc_5m,
            cache_creation_1h_tokens=cc_1h,
            output_tokens=output_tokens,
            total_tokens=total,
        )

        if model not in usage_by_model:
            usage_by_model[model] = TokenUsage()
        usage_by_model[model] += tu

    return usage_by_model


def _resolve_session_jsonl(entry: dict) -> Path | None:
    """Find the JSONL file for a session entry."""
    full_path = entry.get("fullPath")
    if full_path:
        p = Path(full_path)
        if p.exists():
            return p

    project_dir = entry.get("_project_dir")
    session_id = entry.get("sessionId")
    if project_dir and session_id:
        p = Path(project_dir) / f"{session_id}.jsonl"
        if p.exists():
            return p

    return None


def build_session_report(entry: dict, usage: dict[str, TokenUsage]) -> SessionReport:
    """Build a SessionReport from a session entry and parsed JSONL usage."""
    total = TokenUsage()
    for u in usage.values():
        total += u

    is_sidechain = entry.get("isSidechain", False)

    return SessionReport(
        id=entry.get("sessionId", ""),
        title=entry.get("summary", "") or entry.get("firstPrompt", ""),
        created_at=entry.get("created", ""),
        updated_at=entry.get("modified", ""),
        source="subagent" if is_sidechain else "cli",
        parent_id=None,
        agent_nickname=None,
        agent_role=None,
        model_provider="anthropic",
        usage_by_model=usage,
        total_usage=total,
    )
