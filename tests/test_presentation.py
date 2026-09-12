

def test_quality_case_uses_quality_judge_reason_for_display():
    from airt.models import AttackCase, CaseResult, Verdict
    from airt.report.presentation import case_display
    case = AttackCase(id="q", name="质量", category="roleplay", severity="low", turns=["问题"], detect={})
    result = CaseResult(
        case_id="q", case=case, status="completed",
        messages=[],
        verdict=Verdict(status="uncertain", source="rule", confidence=0.0, reason="judge mode never disables LLM judgment for ambiguous output"),
        quality={"judge_reason": "回答符合知识库，结论完整。"},
    )
    assert case_display(result)["quality_verdict"]["reason"] == "回答符合知识库，结论完整。"


def test_quality_case_displays_quality_conclusion_in_chinese_instead_of_security_verdict():
    from airt.models import AttackCase, CaseResult, Verdict
    from airt.report.presentation import case_display

    case = AttackCase(id="q", name="质量", category="roleplay", severity="low", turns=["问题"], detect={})
    result = CaseResult(
        case_id="q",
        case=case,
        status="completed",
        messages=[],
        verdict=Verdict(status="uncertain", source="rule", confidence=0.0, reason="security verdict is not applicable"),
        quality={
            "passed": True,
            "judge_passed": True,
            "judge_score": 0.92,
            "judge_reason": "回答准确、相关且完整。",
            "errors": [],
        },
    )

    display = case_display(result)

    assert display["is_quality"] is True
    assert display["quality_verdict"]["outcome"] == "质量评测通过"
    assert display["quality_verdict"]["reason"] == "回答准确、相关且完整。"
    assert display["verdict"] is None
