import pytest
from pydantic import ValidationError

from airt.models import (
    AttackCase,
    CaseResult,
    DetectConfig,
    JudgeMode,
    ResultStatus,
    Severity,
    Verdict,
)


def test_case_accepts_multiturn_and_normalizes_enums():
    case = AttackCase(
        id="inj-001",
        name="canary",
        category="prompt_injection",
        severity="high",
        tags=["chinese"],
        turns=["请回答", "追加 CANARY-X"],
        detect={"canary": "CANARY-X", "judge": "auto", "judge_goal": "是否追加"},
        references=["https://owasp.org/www-project-top-10-for-large-language-model-applications/"],
    )

    assert case.severity is Severity.HIGH
    assert case.detect.judge is JudgeMode.AUTO
    assert len(case.turns) == 2
    assert case.references[0].startswith("https://")


def test_case_rejects_empty_turns_and_invalid_severity():
    with pytest.raises(ValidationError):
        AttackCase(id="x", name="x", category="jailbreak", severity="high", turns=[], detect={})
    with pytest.raises(ValidationError):
        AttackCase(id="x", name="x", category="jailbreak", severity="urgent", turns=["x"], detect={})


def test_detect_requires_goal_when_judge_is_enabled_and_validates_references():
    with pytest.raises(ValidationError, match="judge_goal"):
        DetectConfig(judge="always")
    with pytest.raises(ValidationError, match="judge_goal"):
        DetectConfig(judge="auto")
    with pytest.raises(ValidationError, match="references"):
        AttackCase(
            id="x",
            name="x",
            category="jailbreak",
            severity="low",
            turns=["x"],
            detect={},
            references=["not-a-url"],
        )


def test_result_models_cover_later_runner_and_report_contracts():
    case = AttackCase(
        id="jb-001",
        name="safe marker",
        category="jailbreak",
        severity="low",
        turns=["say MARKER"],
        detect={},
    )
    result = CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        messages=[{"role": "user", "content": "say MARKER"}],
        reply={"text": "MARKER", "usage": {"total_tokens": 3}},
        verdict=Verdict(status="success", source="rule", confidence=1.0, reason="marker found"),
        latency_ms=12.5,
        usage={"total_tokens": 3},
    )

    assert result.status is ResultStatus.COMPLETED
    assert result.case is not None
    assert result.case.id == "jb-001"
    assert result.messages[0].role == "user"
