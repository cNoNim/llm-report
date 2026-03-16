"""Data structures for usage reports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    tool_tokens: int = 0
    total_tokens: int = 0

    @property
    def cache_creation_tokens(self) -> int:
        return self.cache_creation_5m_tokens + self.cache_creation_1h_tokens

    def __iadd__(self, other: TokenUsage) -> TokenUsage:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cache_creation_5m_tokens += other.cache_creation_5m_tokens
        self.cache_creation_1h_tokens += other.cache_creation_1h_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.tool_tokens += other.tool_tokens
        self.total_tokens += other.total_tokens
        return self

    def is_zero(self) -> bool:
        return self.total_tokens == 0


@dataclass
class SessionReport:
    id: str
    title: str
    created_at: str  # ISO8601
    updated_at: str  # ISO8601
    source: str  # "cli" | "vscode" | "exec" | "mcp" | "subagent" | ...
    parent_id: str | None
    agent_nickname: str | None
    agent_role: str | None
    model_provider: str
    usage_by_model: dict[str, TokenUsage]
    total_usage: TokenUsage


@dataclass
class DailyReport:
    by_model: dict[str, TokenUsage] = field(default_factory=dict)
    total: TokenUsage = field(default_factory=TokenUsage)
    session_count: int = 0
    subagent_count: int = 0


@dataclass
class MonthlyReport:
    by_model: dict[str, TokenUsage] = field(default_factory=dict)
    total: TokenUsage = field(default_factory=TokenUsage)
    session_count: int = 0
    subagent_count: int = 0
    daily: dict[str, DailyReport] = field(default_factory=dict)


@dataclass
class Report:
    generated_at: str
    data_home: str
    sessions: list[SessionReport]
    monthly: dict[str, MonthlyReport]  # key: "YYYY-MM"
    grand_total_by_model: dict[str, TokenUsage]
    grand_total: TokenUsage
    provider: str = "codex"


@dataclass
class CombinedReport:
    generated_at: str
    homes: list[Report]
    monthly: dict[str, MonthlyReport]
    grand_total_by_model: dict[str, TokenUsage]
    grand_total: TokenUsage
    session_count: int = 0
    subagent_count: int = 0
    provider: str = "combined"
