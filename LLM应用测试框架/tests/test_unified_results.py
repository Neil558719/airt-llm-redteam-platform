from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LLM应用测试框架"))
from llmtest.unified_results import quality_result

def test_quality_result_has_evaluation_v1_shape():
    result = quality_result(case_id="q1", target="unified_dify_chatflow", answer="答复", expected="期望", latency_ms=12.5, passed=True)
    assert result["schema_version"] == "evaluation-result-v1"
    assert result["runner"] == "pytest"
    assert result["category"] == "quality"
    assert result["scores"]["correctness"] == 1.0
