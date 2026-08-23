from airt.models import AttackCase, CaseCategory, CaseResult, Reply, ResultStatus, Severity, Verdict, VerdictSource, VerdictStatus
from airt.unified_results import from_airt, from_pytest


def test_airt_result_converts_to_v1_contract():
    case = AttackCase(id="x", name="x", category=CaseCategory.INDIRECT_INJECTION, severity=Severity.HIGH, tags=["unified-chatflow", "security"], turns=["x"])
    result = CaseResult(case_id="x", case=case, status=ResultStatus.COMPLETED, reply=Reply(text="拒绝"), verdict=Verdict(status=VerdictStatus.FAIL, source=VerdictSource.RULE, confidence=0.9, reason="safe"))
    record = from_airt(result)
    assert record["schema_version"] == "evaluation-result-v1"
    assert record["runner"] == "airt"
    assert record["category"] == "security"


def test_pytest_result_uses_same_required_keys():
    record = from_pytest(case_id="q", target="unified_dify_chatflow", category="quality", status="passed", scores={"correctness": 0.9})
    assert {"schema_version", "runner", "target", "case_id", "category", "status"} <= record.keys()
