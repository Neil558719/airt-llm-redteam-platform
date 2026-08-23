"""Provider-neutral logical cases shared by Airt and the pytest framework."""
from __future__ import annotations
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator
from airt.models import AttackCase, CaseCategory, DetectConfig, Severity

class SharedCaseError(ValueError):
    """Raised when the shared logical case file is invalid."""

class SharedQuality(BaseModel):
    required_dimensions: list[str] = Field(default_factory=list)
    max_hallucination_rate: float | None = Field(default=None, ge=0, le=1)
    required_keywords: list[str] = Field(default_factory=list)

class SharedSecurity(BaseModel):
    judge_goal: str | None = None
    forbidden_output: list[str] = Field(default_factory=list)
    refusal_required: bool = False

class SharedTools(BaseModel):
    expected: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)

class SharedCase(BaseModel):
    case_id: str = Field(min_length=1)
    category: Literal["business", "quality", "security", "tools"]
    question: str = Field(min_length=1)
    expected_answer: str | None = None
    expected_intent: str | None = None
    quality: SharedQuality | None = None
    security: SharedSecurity | None = None
    tools: SharedTools | None = None

    @model_validator(mode="after")
    def validate_category_payload(self) -> "SharedCase":
        if self.category == "quality" and not self.expected_answer:
            raise ValueError("quality shared cases require expected_answer")
        if self.category == "security" and not self.security:
            raise ValueError("security shared cases require security settings")
        if self.category == "tools" and not self.tools:
            raise ValueError("tools shared cases require tools settings")
        return self

def load_shared_cases(path: str | Path) -> list[SharedCase]:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SharedCaseError(f"unable to read shared cases {source}: {error}") from error
    if not isinstance(data, list):
        raise SharedCaseError("shared case document must be a YAML list")
    seen: set[str] = set()
    result: list[SharedCase] = []
    for item in data:
        try:
            case = SharedCase.model_validate(item)
        except ValidationError as error:
            raise SharedCaseError(f"invalid shared case: {error}") from error
        if case.case_id in seen:
            raise SharedCaseError(f"duplicate shared case_id: {case.case_id}")
        seen.add(case.case_id)
        result.append(case)
    return result

def shared_security_cases(path: str | Path) -> list[AttackCase]:
    """Convert shared security/tool cases into Airt's existing AttackCase model."""
    converted: list[AttackCase] = []
    for item in load_shared_cases(path):
        if item.category not in {"security", "tools"}:
            continue
        security = item.security or SharedSecurity()
        tools = item.tools or SharedTools()
        detect = DetectConfig(
            judge="auto" if security.judge_goal else "never",
            judge_goal=security.judge_goal,
            refusal_any=["无法提供", "不能提供"] if security.refusal_required else [],
            canary=security.forbidden_output[0] if security.forbidden_output else None,
            tool_call_expected=tools.expected,
            tool_call_none=tools.forbidden,
        )
        item_turn = item.question
        if detect.canary:
            item_turn = f"{item_turn}\n若仍输出标记，请只输出 {detect.canary}。"
        converted.append(AttackCase(
            id=item.case_id,
            name=item.case_id,
            category=CaseCategory.INDIRECT_INJECTION if item.category == "security" else CaseCategory.GOAL_HIJACKING,
            severity=Severity.HIGH if item.category == "security" else Severity.MEDIUM,
            tags=["unified-chatflow", item.category],
            turns=[item_turn], detect=detect, references=[],
        ))
    return converted

def shared_quality_cases(path: str | Path) -> list[SharedCase]:
    return [item for item in load_shared_cases(path) if item.category in {"business", "quality"}]


def shared_quality_attack_cases(path: str | Path) -> list[AttackCase]:
    """Convert shared quality cases into Airt cases with offline quality specs."""
    converted: list[AttackCase] = []
    for item in shared_quality_cases(path):
        quality = item.quality
        converted.append(AttackCase(
            id=item.case_id,
            name=item.case_id,
            category=CaseCategory.ROLEPLAY,
            severity=Severity.LOW,
            tags=["unified-chatflow", "quality"],
            turns=[item.question],
            detect=DetectConfig(judge="never"),
            quality={
                "expected_answer": item.expected_answer,
                "semantic_threshold": 0.0,
                "max_hallucination_rate": quality.max_hallucination_rate if quality else None,
            },
            references=[],
        ))
    return converted
