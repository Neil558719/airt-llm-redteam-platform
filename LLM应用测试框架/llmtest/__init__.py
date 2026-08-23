"""llmtest —— LLM 应用自动化测试框架。

基于 pytest 封装，为聊天机器人 / RAG 助手提供：
- 语义断言 / 相似度断言 / JSON Schema 校验 / LLM-as-Judge 自动打分
- 幻觉检测（事实一致性评估，计算幻觉率）
- HTML 质量报告看板（准确率 / 幻觉率 / 响应延迟）

公共 API 从包根导出：

    from llmtest import (
        assert_semantic_match,      # 语义断言
        assert_similarity,          # 相似度断言
        assert_valid_json,          # JSON 解析断言
        assert_json_schema,         # JSON Schema 校验
        assert_llm_judge,           # LLM-as-Judge 打分断言
        assert_hallucination_rate,  # 幻觉率断言
        detect_hallucination,       # 幻觉检测（测量函数）
        llm_judge,                  # LLM-as-Judge 打分（测量函数）
        JudgeSpec,                  # 打分细则
    )
"""

__version__ = "0.1.0"

from .assertions.schema import assert_valid_json, assert_json_schema
from .assertions.semantic import assert_semantic_match, semantic_match
from .assertions.similarity import assert_similarity, similarity
from .assertions.judge import assert_llm_judge
from .hallucination.detector import detect_hallucination, assert_hallucination_rate
from .judge.evaluator import llm_judge, JudgeSpec
from .config import Config
from .clients import get_client
from .specs import AppResponse
from .metrics.tracker import track_latency
from .apps import apps, register_app

__all__ = [
    "assert_semantic_match",
    "semantic_match",
    "assert_similarity",
    "similarity",
    "assert_valid_json",
    "assert_json_schema",
    "assert_llm_judge",
    "llm_judge",
    "detect_hallucination",
    "assert_hallucination_rate",
    "JudgeSpec",
    "AppResponse",
    "track_latency",
    "apps",
    "register_app",
    "Config",
    "get_client",
    "__version__",
]
