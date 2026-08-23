from pathlib import Path
from airt.shared_cases import load_shared_cases, shared_quality_cases, shared_security_cases
ROOT = Path(__file__).resolve().parents[1]

def test_shared_case_file_has_unique_cases_and_all_categories():
    cases = load_shared_cases(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert len(cases) == 8
    assert {case.category for case in cases} == {"quality", "security", "tools"}
    assert len({case.case_id for case in cases}) == len(cases)

def test_shared_security_cases_convert_to_existing_airt_model():
    cases = shared_security_cases(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert {case.id for case in cases} == {"kb_prompt_injection_001", "system_prompt_exfiltration_001", "order_status_tool_001", "restricted_notice_tool_001", "goal_hijack_001"}
    tool_case = next(case for case in cases if case.id == "order_status_tool_001")
    assert tool_case.detect.tool_call_expected == ["query_order"]

def test_shared_quality_cases_keep_quality_dimensions():
    cases = shared_quality_cases(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert len(cases) == 3
    assert "faithfulness" in cases[0].quality.required_dimensions
from pathlib import Path
from airt.shared_cases import shared_quality_attack_cases

ROOT = Path(__file__).resolve().parents[1]

def test_shared_quality_cases_convert_to_attack_cases_with_quality_specs():
    cases = shared_quality_attack_cases(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert [case.id for case in cases] == ["kb_return_window_001", "kb_return_condition_001", "kb_return_shipping_001"]
    assert cases[0].quality.expected_answer.startswith("未使用的标准商品")
    assert cases[0].quality.max_hallucination_rate == 0.25

