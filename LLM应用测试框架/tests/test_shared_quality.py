from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LLM应用测试框架"))
from llmtest.shared_cases import load_quality_questions


@pytest.mark.parametrize(
    "case_id,question,expected,required_keywords,forbidden_keywords",
    load_quality_questions(ROOT / "shared_cases" / "unified_chatflow.yaml"),
    ids=lambda item: item[0] if isinstance(item, tuple) else str(item),
)
def test_unified_chatflow_quality_case_is_data_driven(app_under_test, case_id, question, expected, required_keywords, forbidden_keywords):
    """统一 Chatflow 质量用例由共享 YAML 驱动，检查事实覆盖和禁止编造。"""
    result = app_under_test.ask(question)
    expected_tokens = required_keywords or [expected[:4]]
    assert any(token in result.answer for token in expected_tokens), f"{case_id}: answer did not contain expected facts"
    unexpected = [token for token in forbidden_keywords if token in result.answer]
    assert not unexpected, f"{case_id}: answer contained unsupported facts: {unexpected}"


