"""Configuration loading for llm-report."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_BASENAME = "llm-report.toml"
DEFAULT_CONFIG_FALLBACK_BASENAME = "llm-report.default.toml"


class ConfigLoadError(RuntimeError):
    """Raised when a config file cannot be read or parsed."""


@dataclass(frozen=True)
class ReportConfig:
    codex_homes: tuple[Path, ...] = ()
    claude_homes: tuple[Path, ...] = ()
    gemini_homes: tuple[Path, ...] = ()
    pricing_paths: dict[str, Path] = field(default_factory=dict)


def load_config(path: Path) -> ReportConfig:
    """Load report configuration from a TOML file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigLoadError(f"Failed to read config file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(f"Failed to parse config file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigLoadError(f"Config file {path} must contain a TOML table")

    base_dir = path.expanduser().resolve().parent
    homes = _as_table(data.get("homes"), "homes", path)
    pricing = _as_table(data.get("pricing"), "pricing", path)

    return ReportConfig(
        codex_homes=_parse_home_list(homes, "codex", base_dir, path),
        claude_homes=_parse_home_list(homes, "claude", base_dir, path),
        gemini_homes=_parse_home_list(homes, "gemini", base_dir, path),
        pricing_paths=_parse_pricing_paths(pricing, base_dir, path),
    )


def _as_table(value: Any, section: str, path: Path) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ConfigLoadError(f"Section [{section}] in {path} must be a TOML table")


def _parse_home_list(
    homes: dict[str, Any],
    provider: str,
    base_dir: Path,
    path: Path,
) -> tuple[Path, ...]:
    value = homes.get(provider)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigLoadError(
            f"homes.{provider} in {path} must be an array of strings",
        )
    return tuple(_resolve_path(item, base_dir) for item in value)


def _parse_pricing_paths(
    pricing: dict[str, Any],
    base_dir: Path,
    path: Path,
) -> dict[str, Path]:
    pricing_paths: dict[str, Path] = {}
    for provider in ("codex", "claude", "gemini"):
        value = pricing.get(provider)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ConfigLoadError(f"pricing.{provider} in {path} must be a string path")
        pricing_paths[provider] = _resolve_path(value, base_dir)
    return pricing_paths


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def find_config_path(cwd: Path | None = None) -> Path | None:
    """Find the preferred config path in the working directory."""
    search_dir = Path.cwd() if cwd is None else cwd
    primary = search_dir / DEFAULT_CONFIG_BASENAME
    if primary.is_file():
        return primary

    fallback = search_dir / DEFAULT_CONFIG_FALLBACK_BASENAME
    if fallback.is_file():
        return fallback

    return None
