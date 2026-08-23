"""Shared domain models for authorized LLM red-team runs."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class CaseCategory(str, Enum):
    """Attack categories supported by the default case library."""

    PROMPT_INJECTION = "prompt_injection"
    INDIRECT_INJECTION = "indirect_injection"
    JAILBREAK = "jailbreak"
    ROLEPLAY = "roleplay"
    ENCODING_OBFUSCATION = "encoding_obfuscation"
    GOAL_HIJACKING = "goal_hijacking"
    DATA_EXFILTRATION = "data_exfiltration"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class JudgeMode(str, Enum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class VerdictStatus(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class VerdictSource(str, Enum):
    RULE = "rule"
    JUDGE = "judge"


class ResultStatus(str, Enum):
    COMPLETED = "completed"
    ERROR = "error"


class DetectConfig(BaseModel):
    """Per-case configuration for deterministic and LLM evaluation."""

    canary: str | None = Field(default=None, min_length=1)
    refusal_any: list[str] = Field(default_factory=list)
    tool_call_any: list[str] = Field(default_factory=list)
    tool_call_none: list[str] = Field(default_factory=list)
    tool_call_required: list[str] = Field(default_factory=list)
    tool_call_expected: list[str] = Field(default_factory=list)
    tool_argument_any: list[str] = Field(default_factory=list)
    judge: JudgeMode = JudgeMode.NEVER
    judge_goal: str | None = None

    @field_validator("refusal_any", "tool_call_any", "tool_call_none", "tool_call_required", "tool_call_expected", "tool_argument_any")
    @classmethod
    def detector_values_are_nonempty(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("detector values must be non-empty strings")
        return values

    @model_validator(mode="after")
    def enabled_judge_requires_goal(self) -> "DetectConfig":
        if self.judge is not JudgeMode.NEVER and not self.judge_goal:
            raise ValueError("judge_goal is required when judge is not never")
        return self


class QualitySpec(BaseModel):
    """Optional quality checks executed after a security case completes."""

    expected_answer: str | None = None
    semantic_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_hallucination_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    json_schema: dict[str, Any] | None = None


class AttackCase(BaseModel):
    """A data-driven, harmless red-team test case."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: CaseCategory
    severity: Severity
    tags: list[str] = Field(default_factory=list)
    turns: list[str] = Field(min_length=1)
    detect: DetectConfig = Field(default_factory=DetectConfig)
    quality: QualitySpec | None = None
    references: list[str] = Field(default_factory=list)

    @field_validator("turns")
    @classmethod
    def turns_are_nonempty(cls, turns: list[str]) -> list[str]:
        if any(not turn for turn in turns):
            raise ValueError("turns must contain only non-empty strings")
        return turns

    @field_validator("references")
    @classmethod
    def references_are_http_urls(cls, references: list[str]) -> list[str]:
        for reference in references:
            parsed = urlparse(reference)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("references must be HTTP(S) URLs")
        return references


class Message(BaseModel):
    """One OpenAI-compatible chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class ToolCall(BaseModel):
    """A redacted-at-presentation observation of one target-side tool call."""

    id: str | None = None
    name: str = Field(min_length=1)
    arguments: Any = None
    result: Any = None
    status: str = "observed"
    provider: str | None = None


class Reply(BaseModel):
    """A normalized response returned by a target adapter."""

    text: str
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)


class Verdict(BaseModel):
    status: VerdictStatus
    source: VerdictSource
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)


class RunMetadata(BaseModel):
    """Stable description of how a run was performed."""

    test_type: str = "LLM red-team security assessment"
    test_method: str = "Automated API-based black-box testing"
    target_profile: str = "text"
    run_mode: str = "quality"
    security_judge_policy: str = "case"
    quality_judge_mode: str = "offline"
    run_id: str = "legacy-run"
    started_at: str | None = None
    finished_at: str | None = None


class CaseResult(BaseModel):
    """The complete durable result for one attack case execution."""

    case_id: str = Field(min_length=1)
    case: AttackCase | None = None
    status: ResultStatus
    run_metadata: RunMetadata | None = None
    messages: list[Message] = Field(default_factory=list)
    reply: Reply | None = None
    verdict: Verdict | None = None
    error: str | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)
    usage: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] | None = None
    security_judge_used: bool = False
    quality_judge_used: bool = False
    failure_kind: str | None = None


class MetricGroup(BaseModel):
    """Counts and ASR for one category, severity, or tag group."""

    total: int = Field(ge=0, default=0)
    success: int = Field(ge=0, default=0)
    fail: int = Field(ge=0, default=0)
    uncertain: int = Field(ge=0, default=0)
    error: int = Field(ge=0, default=0)
    asr: float = Field(ge=0.0, le=1.0, default=0.0)


class RunSummary(BaseModel):
    """Aggregate security metrics and groups for a completed run."""

    total: int = Field(ge=0, default=0)
    success: int = Field(ge=0, default=0)
    fail: int = Field(ge=0, default=0)
    uncertain: int = Field(ge=0, default=0)
    error: int = Field(ge=0, default=0)
    asr: float = Field(ge=0.0, le=1.0, default=0.0)
    risk_score: float = Field(ge=0.0, le=100.0, default=100.0)
    by_category: dict[str, MetricGroup] = Field(default_factory=dict)
    by_severity: dict[str, MetricGroup] = Field(default_factory=dict)
    by_tag: dict[str, MetricGroup] = Field(default_factory=dict)
    top_successes: list[CaseResult] = Field(default_factory=list)



