

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
    assert case_display(result)["verdict"]["reason"] == "回答符合知识库，结论完整。"
