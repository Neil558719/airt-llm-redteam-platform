from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK = ROOT / "LLM应用测试框架"
sys.path.insert(0, str(FRAMEWORK))

from llmtest.shared_cases import load_quality_questions, load_shared_cases


def test_pytest_framework_reads_repository_shared_cases():
    cases = load_shared_cases(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert len(cases) == 24
    assert {item["category"] for item in cases} == {"quality", "security", "tools"}


def test_quality_questions_are_data_driven_from_same_file():
    questions = load_quality_questions(ROOT / "shared_cases" / "unified_chatflow.yaml")
    assert [item[0] for item in questions] == [
        "kb_return_window_001",
        "kb_return_condition_001",
        "kb_return_shipping_001",
    ]
