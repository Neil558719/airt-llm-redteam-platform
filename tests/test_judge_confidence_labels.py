from airt.judge.llm import JudgeResponse
from airt.models import AttackCase, CaseCategory, CaseResult, Reply, ResultStatus, Severity, Verdict, VerdictSource, VerdictStatus
from airt.unified_results import from_airt


def test_qualitative_confidence_labels_are_normalized():
    assert JudgeResponse(verdict="fail", confidence="high", reason="resisted").confidence == 0.9
    assert JudgeResponse(verdict="fail", confidence="medium", reason="resisted").confidence == 0.7
    assert JudgeResponse(verdict="fail", confidence="low", reason="unclear").confidence == 0.4


def test_known_json_object_type_metadata_is_ignored():
    response = JudgeResponse(
        type="json_object", verdict="fail", confidence=0.9, reason="resisted"
    )
    assert response.verdict == "fail"


def test_security_score_represents_boundary_result_not_judge_confidence():
    case = AttackCase(
        id="safe", name="safe", category=CaseCategory.INDIRECT_INJECTION,
        severity=Severity.HIGH, tags=["security"], turns=["x"],
    )
    result = CaseResult(
        case_id="safe", case=case, status=ResultStatus.COMPLETED,
        reply=Reply(text="拒绝", usage={}),
        verdict=Verdict(status=VerdictStatus.FAIL, source=VerdictSource.JUDGE, confidence=0.82, reason="safe"),
    )
    assert from_airt(result)["scores"]["security"] == 100.0
