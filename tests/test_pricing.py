"""Tests for pricing catalog loading and cost estimation."""

import json

import pytest

from llm_report.models import TokenUsage
from llm_report.pricing import (
    ModelPricing,
    PricingLoadError,
    estimate_cost_usd,
    find_default_pricing_path,
    load_default_pricing,
    load_pricing,
)


def test_load_pricing_reads_flat_models_file(tmp_path):
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

    catalog = load_pricing(pricing_path)

    assert catalog.source_url == "https://developers.openai.com/api/docs/pricing/"
    assert catalog.models["gpt-5.4"].input == 2.5
    assert catalog.models["gpt-5.4"].cached_input == 0.25
    assert catalog.models["gpt-5.4"].output == 15.0


def test_load_pricing_rejects_missing_models(tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(json.dumps({"unit": "usd_per_1m_tokens"}))

    with pytest.raises(PricingLoadError, match="top-level 'models' object"):
        load_pricing(pricing_path)


def test_estimate_cost_usd_uses_uncached_and_cached_input_prices():
    cost = estimate_cost_usd(
        TokenUsage(
            input_tokens=1_000_000,
            cached_input_tokens=200_000,
            output_tokens=100_000,
            total_tokens=1_100_000,
        ),
        ModelPricing(input=2.5, cached_input=0.25, output=15.0),
    )

    assert cost == pytest.approx(3.55)


def test_load_default_pricing_prefers_current_working_directory(tmp_path, monkeypatch):
    pricing_path = tmp_path / "pricing.openai.json"
    pricing_path.write_text(json.dumps({
        "source_url": "https://example.com/openai-pricing",
        "unit": "usd_per_1m_tokens",
        "models": {
            "gpt-5.4": {
                "input": 2.5,
                "cached_input": 0.25,
                "output": 15.0,
            },
        },
    }))
    monkeypatch.chdir(tmp_path)

    found = find_default_pricing_path("codex")
    catalog = load_default_pricing("codex")

    assert found == pricing_path
    assert catalog is not None
    assert catalog.source_url == "https://example.com/openai-pricing"


def test_load_default_pricing_supports_gemini(tmp_path, monkeypatch):
    pricing_path = tmp_path / "pricing.gemini.json"
    pricing_path.write_text(json.dumps({
        "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "unit": "usd_per_1m_tokens",
        "models": {
            "gemini-2.5-pro": {
                "input": 1.25,
                "cached_input": 0.125,
                "output": 10.0,
            },
        },
    }))
    monkeypatch.chdir(tmp_path)

    found = find_default_pricing_path("gemini")
    catalog = load_default_pricing("gemini")

    assert found == pricing_path
    assert catalog is not None
    assert catalog.source_url == "https://ai.google.dev/gemini-api/docs/pricing"
