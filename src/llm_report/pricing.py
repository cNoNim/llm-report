"""Pricing catalog loading and usage cost estimation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_report.models import TokenUsage


DEFAULT_PRICING_FILES = {
    "codex": "pricing.openai.json",
    "claude": "pricing.anthropic.json",
    "gemini": "pricing.gemini.json",
}


@dataclass(frozen=True)
class ModelPricing:
    input: float | None
    cached_input: float | None
    output: float | None
    cache_creation_5m: float | None = None
    cache_creation_1h: float | None = None


@dataclass(frozen=True)
class PricingCatalog:
    source_url: str | None
    extracted_at: str | None
    unit: str | None
    models: dict[str, ModelPricing]


@dataclass(frozen=True)
class CostBreakdown:
    uncached_input_cost: float
    cached_input_cost: float
    output_cost: float
    total_cost: float
    cache_creation_cost: float = 0.0


class PricingLoadError(RuntimeError):
    """Raised when a pricing JSON file cannot be parsed."""


def find_default_pricing_path(provider: str) -> Path | None:
    """Locate the default pricing file for a provider."""
    filename = DEFAULT_PRICING_FILES.get(provider)
    if filename is None:
        return None

    repo_root = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []
    for candidate in (Path.cwd() / filename, repo_root / filename):
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_default_pricing(provider: str) -> PricingCatalog | None:
    """Load the default pricing catalog for a provider, if present."""
    path = find_default_pricing_path(provider)
    if path is None:
        return None
    return load_pricing(path)


def load_pricing(path: Path) -> PricingCatalog:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PricingLoadError(f"Failed to read pricing file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PricingLoadError(f"Failed to parse pricing file {path}: {exc}") from exc

    models_raw = data.get("models")
    if not isinstance(models_raw, dict):
        raise PricingLoadError(f"Pricing file {path} must contain a top-level 'models' object")

    models: dict[str, ModelPricing] = {}
    for model, payload in models_raw.items():
        if not isinstance(model, str) or not isinstance(payload, dict):
            raise PricingLoadError(f"Pricing entry for model {model!r} is invalid")
        models[model] = ModelPricing(
            input=_parse_price(payload, "input", model),
            cached_input=_parse_price(payload, "cached_input", model),
            output=_parse_price(payload, "output", model),
            cache_creation_5m=_parse_price(payload, "cache_creation_5m", model),
            cache_creation_1h=_parse_price(payload, "cache_creation_1h", model),
        )

    return PricingCatalog(
        source_url=_optional_str(data.get("source_url")),
        extracted_at=_optional_str(data.get("extracted_at")),
        unit=_optional_str(data.get("unit")),
        models=models,
    )


def estimate_cost_usd(usage: TokenUsage, pricing: ModelPricing) -> float | None:
    breakdown = estimate_cost_breakdown(usage, pricing)
    if breakdown is None:
        return None
    return breakdown.total_cost


def estimate_cost_breakdown(
    usage: TokenUsage,
    pricing: ModelPricing,
) -> CostBreakdown | None:
    cc_total = usage.cache_creation_tokens
    uncached_input_tokens = max(
        usage.input_tokens - usage.cached_input_tokens - cc_total, 0,
    )

    if uncached_input_tokens > 0 and pricing.input is None:
        return None
    if usage.cached_input_tokens > 0 and pricing.cached_input is None:
        return None
    if usage.output_tokens > 0 and pricing.output is None:
        return None

    uncached_input_cost = 0.0
    cached_input_cost = 0.0
    cache_creation_cost = 0.0
    output_cost = 0.0

    if pricing.input is not None:
        uncached_input_cost = uncached_input_tokens / 1_000_000 * pricing.input
    if pricing.cached_input is not None:
        cached_input_cost = usage.cached_input_tokens / 1_000_000 * pricing.cached_input
    if pricing.output is not None:
        output_cost = usage.output_tokens / 1_000_000 * pricing.output

    # Cache creation: 5m and 1h have different prices; fall back to base input
    cc_5m_price = pricing.cache_creation_5m if pricing.cache_creation_5m is not None else pricing.input
    cc_1h_price = pricing.cache_creation_1h if pricing.cache_creation_1h is not None else pricing.input
    if usage.cache_creation_5m_tokens > 0 and cc_5m_price is not None:
        cache_creation_cost += usage.cache_creation_5m_tokens / 1_000_000 * cc_5m_price
    if usage.cache_creation_1h_tokens > 0 and cc_1h_price is not None:
        cache_creation_cost += usage.cache_creation_1h_tokens / 1_000_000 * cc_1h_price

    total = uncached_input_cost + cached_input_cost + cache_creation_cost + output_cost
    return CostBreakdown(
        uncached_input_cost=uncached_input_cost,
        cached_input_cost=cached_input_cost,
        output_cost=output_cost,
        total_cost=total,
        cache_creation_cost=cache_creation_cost,
    )


def estimate_by_model_costs(
    usage_by_model: dict[str, TokenUsage],
    catalog: PricingCatalog,
) -> tuple[dict[str, float | None], list[str]]:
    costs: dict[str, float | None] = {}
    missing_models: list[str] = []

    for model, usage in usage_by_model.items():
        pricing = catalog.models.get(model)
        if pricing is None:
            costs[model] = None
            missing_models.append(model)
            continue

        cost = estimate_cost_usd(usage, pricing)
        costs[model] = cost
        if cost is None:
            missing_models.append(model)

    return costs, missing_models


def sum_costs(costs: dict[str, float | None]) -> float | None:
    known_costs = [cost for cost in costs.values() if cost is not None]
    if not known_costs and costs:
        return None
    return sum(known_costs)


def sum_cost_breakdowns(
    breakdowns: dict[str, CostBreakdown | None],
) -> CostBreakdown | None:
    known_breakdowns = [breakdown for breakdown in breakdowns.values() if breakdown is not None]
    if not known_breakdowns and breakdowns:
        return None

    uncached_input_cost = 0.0
    cached_input_cost = 0.0
    cache_creation_cost = 0.0
    output_cost = 0.0
    for breakdown in known_breakdowns:
        uncached_input_cost += breakdown.uncached_input_cost
        cached_input_cost += breakdown.cached_input_cost
        cache_creation_cost += breakdown.cache_creation_cost
        output_cost += breakdown.output_cost

    total = uncached_input_cost + cached_input_cost + cache_creation_cost + output_cost
    return CostBreakdown(
        uncached_input_cost=uncached_input_cost,
        cached_input_cost=cached_input_cost,
        output_cost=output_cost,
        total_cost=total,
        cache_creation_cost=cache_creation_cost,
    )


def estimate_by_model_breakdowns(
    usage_by_model: dict[str, TokenUsage],
    catalog: PricingCatalog,
) -> tuple[dict[str, CostBreakdown | None], list[str]]:
    breakdowns: dict[str, CostBreakdown | None] = {}
    missing_models: list[str] = []

    for model, usage in usage_by_model.items():
        pricing = catalog.models.get(model)
        if pricing is None:
            breakdowns[model] = None
            missing_models.append(model)
            continue

        breakdown = estimate_cost_breakdown(usage, pricing)
        breakdowns[model] = breakdown
        if breakdown is None:
            missing_models.append(model)

    return breakdowns, missing_models


def _parse_price(payload: dict[str, Any], field: str, model: str) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise PricingLoadError(f"Pricing field {field!r} for model {model!r} must be a number or null")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
