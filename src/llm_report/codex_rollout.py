"""Codex rollout JSONL parser that extracts per-model token usage."""

from __future__ import annotations

import json
from pathlib import Path

from llm_report.models import TokenUsage


def parse_rollout(path: Path) -> dict[str, TokenUsage]:
    """Parse a rollout JSONL file and return usage broken down by model.

    Tracks the current model via turn_context events and accumulates
    last_token_usage deltas from token_count events.
    """
    current_model = "unknown"
    usage_by_model: dict[str, TokenUsage] = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            item_type = item.get("type")
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue

            if item_type == "turn_context":
                model = payload.get("model")
                if model:
                    current_model = model

            elif item_type == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                if info is None:
                    continue
                last = info.get("last_token_usage")
                if last is None:
                    continue
                if last.get("total_tokens", 0) == 0:
                    continue

                if current_model not in usage_by_model:
                    usage_by_model[current_model] = TokenUsage()

                usage = usage_by_model[current_model]
                usage.input_tokens += last.get("input_tokens", 0)
                usage.cached_input_tokens += last.get("cached_input_tokens", 0)
                usage.output_tokens += last.get("output_tokens", 0)
                usage.reasoning_output_tokens += last.get("reasoning_output_tokens", 0)
                usage.total_tokens += last.get("total_tokens", 0)

    return usage_by_model


def extract_last_model(path: Path) -> str:
    """Extract the last model name from turn_context events in a rollout."""
    last_model = "unknown"
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") == "turn_context":
                model = item.get("payload", {}).get("model")
                if model:
                    last_model = model
    return last_model
