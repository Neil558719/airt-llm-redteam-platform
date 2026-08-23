"""示例测试的共享配置：注册"模拟问答应用"为被测对象。

`tests/` 套件是**双模式**的：
- `pytest tests/`（默认）→ 被测 = mock-cs（Mock），裁判 = Mock，确定性、无需 API key；
- `pytest tests/ --app-model <模型> ...`（或 LLM_APP_MODEL 环境变量）→ 被测 = 真实模型，
  裁判 = 配置的裁判模型（`--llm-*`）。

框架的 `app_under_test` fixture 优先级：`--app <注册名>` > `--app-model <裸模型>` > 注册默认应用 > Mock。
"""

from llmtest.apps import register_app
from llmtest.clients import get_client
from llmtest.config import Config
from llmtest.unified_results import quality_result
from pathlib import Path
import pytest
import json
import os

# Mock 场景预设：关键词 → 被测"应用"返回的内容（确定性、可复现）。
# 关键词与 tests/ 里各用例的问题对齐；真实模型模式下这些预设不生效（走 --app-model）。
MOCK_RESPONSES = {
    # 聊天机器人
    "什么是 RAG": "RAG 是检索增强生成，结合了检索与生成。",
    "你好": "你好！我是智能助手，很高兴为你服务。我可以解答问题、处理任务。",
    "介绍": "我是 AI 助手，可以帮你解答问题、处理任务。",
    "1 + 1": "1 + 1 等于 2。",
    # 结构化输出
    "JSON 对象": '{"name": "RAG", "category": "framework", "features": ["semantic", "judge"]}',
    # RAG 场景：回答含 3 条事实断言，其中 1 条（预约）不在资料里 → 幻觉率约 33%
    "退货期限": "未使用的标准商品可在签收后 14 天内申请退货。定制商品、已拆封的个人护理商品以及已完成的数字服务不适用常规无理由退货。",
    "退货需要满足什么条件": "未使用的标准商品可按公开流程申请退货；定制商品、已拆封个人护理商品和数字服务不适用常规无理由退货。",
    "退货运费": "当前公开资料未明确退货运费承担方，无法从当前资料确认。",
    "default": "这是 Mock 模式的默认回复。",
}


@register_app("mock-cs", default=True)
def _build_mock_cs_app():
    """模拟被测问答/RAG 应用（Mock 模式，确定性可复现）。"""
    return get_client(Config(mode="mock", mock_responses=MOCK_RESPONSES))



def _shared_result_path() -> Path:
    configured = os.environ.get("UNIFIED_RESULTS_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "reports" / "evaluation-result-v1.jsonl"


def pytest_runtest_makereport(item, call):
    """Export shared quality test outcomes in the repository-wide result schema."""
    if "test_shared_quality.py" not in str(item.fspath) or call.when != "call":
        return
    report = pytest.TestReport.from_item_and_call(item, call)
    case_id = str(item.callspec.params.get("case_id", item.name)) if hasattr(item, "callspec") else item.name
    question = str(item.callspec.params.get("question", "")) if hasattr(item, "callspec") else ""
    expected = str(item.callspec.params.get("expected", "")) if hasattr(item, "callspec") else ""
    answer = ""
    status = report.outcome == "passed"
    record = quality_result(
        case_id=case_id,
        target=os.environ.get("UNIFIED_TARGET", "unified_dify_chatflow"),
        answer=answer,
        expected=expected,
        latency_ms=report.duration * 1000,
        passed=status,
        error=str(call.excinfo.value) if call.excinfo else None,
    )
    path = _shared_result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


