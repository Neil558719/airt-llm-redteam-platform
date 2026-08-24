from airt.models import AttackCase, CaseCategory, CaseResult, Reply, ResultStatus, Severity, Verdict, VerdictSource, VerdictStatus
from airt.unified_results import from_airt, from_pytest


def test_airt_result_converts_to_v1_contract():
    case = AttackCase(id="x", name="x", category=CaseCategory.INDIRECT_INJECTION, severity=Severity.HIGH, tags=["unified-chatflow", "security"], turns=["x"])
    result = CaseResult(case_id="x", case=case, status=ResultStatus.COMPLETED, reply=Reply(text="拒绝"), verdict=Verdict(status=VerdictStatus.FAIL, source=VerdictSource.RULE, confidence=0.9, reason="safe"))
    record = from_airt(result)
    assert record["schema_version"] == "evaluation-result-v1"
    assert record["runner"] == "airt"
    assert record["category"] == "security"


def test_blocked_security_attack_is_a_passed_unified_record():
    case = AttackCase(
        id="safe",
        name="safe",
        category=CaseCategory.INDIRECT_INJECTION,
        severity=Severity.HIGH,
        tags=["unified-chatflow", "security"],
        turns=["x"],
    )
    result = CaseResult(
        case_id="safe",
        case=case,
        status=ResultStatus.COMPLETED,
        reply=Reply(text="拒绝"),
        verdict=Verdict(
            status=VerdictStatus.FAIL,
            source=VerdictSource.RULE,
            confidence=0.9,
            reason="safe",
        ),
    )
    assert from_airt(result)["status"] == "passed"


def test_quality_result_uses_quality_passed_flag():
    case = AttackCase(
        id="q",
        name="q",
        category=CaseCategory.ROLEPLAY,
        severity=Severity.LOW,
        tags=["unified-chatflow", "quality"],
        turns=["x"],
        quality={"expected_answer": "x"},
    )
    result = CaseResult(
        case_id="q",
        case=case,
        status=ResultStatus.COMPLETED,
        reply=Reply(text="x"),
        verdict=Verdict(
            status=VerdictStatus.UNCERTAIN,
            source=VerdictSource.RULE,
            confidence=0.0,
            reason="quality is evaluated separately",
        ),
        quality={
            "passed": True,
            "semantic_score": 0.9,
            "judge_score": 0.95,
        },
    )
    record = from_airt(result)
    assert record["category"] == "quality"
    assert record["status"] == "passed"
    assert record["scores"]["quality"] == 0.95


def test_pytest_result_uses_same_required_keys():
    record = from_pytest(case_id="q", target="unified_dify_chatflow", category="quality", status="passed", scores={"correctness": 0.9})
    assert {"schema_version", "runner", "target", "case_id", "category", "status"} <= record.keys()
