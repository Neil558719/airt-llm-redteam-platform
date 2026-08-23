"""LLM-as-Judge 评测：测量函数 + 预设细则。"""

from __future__ import annotations

from typing import Optional

from ..metrics.tracker import tracker
from ..registry import get_default_client
from ..specs import JudgeResult, JudgeSpec


def llm_judge(
    response: str,
    spec: JudgeSpec,
    *,
    client=None,
    context: Optional[str] = None,
    question: Optional[str] = None,
) -> JudgeResult:
    """按细则对回答打分，并把结果记入指标采集（聚合准确率）。

    这是测量函数；断言请用 `assert_llm_judge`。
    评判"准确性/相关性"时建议传 `question`（产生该回答的用户问题），裁判需要它核对答案是否正确。
    """
    client = client or get_default_client()
    result = client.judge(response, spec, context, question)
    tracker.add_judge(result)
    tracker.record_metric(f"judge.{spec.name}", result.score, meta=spec.criteria)
    return result


__all__ = ["llm_judge", "JudgeSpec"]
