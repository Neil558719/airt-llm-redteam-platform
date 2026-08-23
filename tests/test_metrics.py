import pytest

from airt.metrics import summarize
from airt.models import AttackCase, CaseResult, Verdict


def result(
    case_id: str,
    category: str,
    severity: str,
    verdict_status: str,
    *,
    tags: list[str] | None = None,
) -> CaseResult:
    case = AttackCase(
        id=case_id,
        name=case_id,
        category=category,
        severity=severity,
        tags=tags or ["shared"],
        turns=["x"],
        detect={},
    )
    if verdict_status == "error":
        return CaseResult(case_id=case.id, case=case, status="error")
    return CaseResult(
        case_id=case.id,
        case=case,
        status="completed",
        verdict=Verdict(
            status=verdict_status,
            source="rule",
            confidence=1.0,
            reason="test",
        ),
    )


def test_asr_excludes_uncertain_and_error_and_risk_uses_exact_severity_weights():
    summary = summarize(
        [
            result("critical-success", "jailbreak", "critical", "success"),
            result("high-fail", "jailbreak", "high", "fail"),
            result("medium-success", "roleplay", "medium", "success"),
            result("low-fail", "roleplay", "low", "fail"),
            result("uncertain", "roleplay", "low", "uncertain"),
            result("error", "roleplay", "low", "error"),
        ]
    )

    assert (summary.total, summary.success, summary.fail, summary.uncertain, summary.error) == (
        6,
        2,
        2,
        1,
        1,
    )
    assert summary.asr == 0.5
    assert summary.risk_score == 100 - 100 * (8 + 2) / (8 + 4 + 2 + 1)


def test_zero_evaluable_denominator_has_zero_asr_and_perfect_risk_score():
    summary = summarize(
        [
            result("uncertain", "jailbreak", "high", "uncertain"),
            result("error", "roleplay", "low", "error"),
        ]
    )

    assert summary.asr == 0.0
    assert summary.risk_score == 100.0


def test_groups_results_by_category_severity_and_each_tag():
    summary = summarize(
        [
            result(
                "critical-success",
                "jailbreak",
                "critical",
                "success",
                tags=["shared", "critical-tag"],
            ),
            result(
                "high-fail",
                "jailbreak",
                "high",
                "fail",
                tags=["shared", "high-tag"],
            ),
            result(
                "low-uncertain",
                "roleplay",
                "low",
                "uncertain",
                tags=["low-tag"],
            ),
            result(
                "low-error",
                "roleplay",
                "low",
                "error",
                tags=["low-tag"],
            ),
        ]
    )

    jailbreak = summary.by_category["jailbreak"]
    assert (jailbreak.success, jailbreak.fail, jailbreak.uncertain, jailbreak.error) == (1, 1, 0, 0)
    assert jailbreak.asr == 0.5

    critical = summary.by_severity["critical"]
    assert (critical.success, critical.fail, critical.uncertain, critical.error) == (1, 0, 0, 0)
    assert critical.asr == 1.0

    shared = summary.by_tag["shared"]
    assert (shared.success, shared.fail, shared.uncertain, shared.error) == (1, 1, 0, 0)
    assert shared.asr == 0.5

    low_tag = summary.by_tag["low-tag"]
    assert (low_tag.success, low_tag.fail, low_tag.uncertain, low_tag.error) == (0, 0, 1, 1)
    assert low_tag.asr == 0.0


def test_top_successes_are_sorted_by_severity_then_case_id():
    summary = summarize(
        [
            result("critical-z", "jailbreak", "critical", "success"),
            result("high-z", "jailbreak", "high", "success"),
            result("critical-a", "jailbreak", "critical", "success"),
            result("low", "jailbreak", "low", "success"),
            result("fail", "jailbreak", "critical", "fail"),
        ]
    )

    assert [item.case_id for item in summary.top_successes] == [
        "critical-a",
        "critical-z",
        "high-z",
        "low",
    ]
