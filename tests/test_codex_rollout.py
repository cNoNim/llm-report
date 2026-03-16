"""Tests for Codex rollout JSONL parsing."""

from pathlib import Path

from llm_report.models import TokenUsage
from llm_report.codex_rollout import extract_last_model, parse_rollout

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rollout_multi_model():
    usage = parse_rollout(FIXTURES / "sample.jsonl")

    assert set(usage.keys()) == {"gpt-5.4", "o3"}

    assert usage["gpt-5.4"] == TokenUsage(
        input_tokens=1000,
        cached_input_tokens=500,
        output_tokens=100,
        reasoning_output_tokens=50,
        total_tokens=1100,
    )

    # o3 has two token_count events: 2200 + 3300
    assert usage["o3"] == TokenUsage(
        input_tokens=5000,
        cached_input_tokens=2500,
        output_tokens=500,
        reasoning_output_tokens=250,
        total_tokens=5500,
    )


def test_parse_rollout_empty_file(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert parse_rollout(empty) == {}


def test_parse_rollout_skips_null_info(tmp_path):
    """token_count events with info=null should be skipped."""
    content = '{"timestamp":"T","type":"turn_context","payload":{"cwd":"/tmp","model":"m1","approval_policy":"on_failure","sandbox_policy":{"type":"read_only"},"summary":"auto"}}\n'
    content += '{"timestamp":"T","type":"event_msg","payload":{"type":"token_count","info":null,"rate_limits":null}}\n'
    f = tmp_path / "null_info.jsonl"
    f.write_text(content)
    assert parse_rollout(f) == {}


def test_parse_rollout_skips_zero_total(tmp_path):
    """token_count events with total_tokens=0 should be skipped."""
    content = '{"timestamp":"T","type":"turn_context","payload":{"cwd":"/tmp","model":"m1","approval_policy":"on_failure","sandbox_policy":{"type":"read_only"},"summary":"auto"}}\n'
    content += '{"timestamp":"T","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"total_tokens":0},"last_token_usage":{"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"total_tokens":0},"model_context_window":258400},"rate_limits":null}}\n'
    f = tmp_path / "zero.jsonl"
    f.write_text(content)
    assert parse_rollout(f) == {}


def test_extract_last_model():
    model = extract_last_model(FIXTURES / "sample.jsonl")
    assert model == "o3"


def test_extract_last_model_no_context(tmp_path):
    f = tmp_path / "no_ctx.jsonl"
    f.write_text('{"timestamp":"T","type":"event_msg","payload":{"type":"task_started"}}\n')
    assert extract_last_model(f) == "unknown"
