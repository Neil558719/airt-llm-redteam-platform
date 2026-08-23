"""LLM-as-Judge 断言：按细则给回答打分并断言达标。"""

from __future__ import annotations

from typing import Optional, Union

from ..metrics.tracker import tracker
from ..specs import JudgeResult, JudgeSpec


def assert_llm_judge(
    response: str,
    spec: Union[JudgeSpec, str],
    *,
    client=None,
    min_score: Optional[float] = None,
    context: Optional[str] = None,
    question: Optional[str] = None,
) -> JudgeResult:
    """按细则对回答打分，断言分数 ≥ 阈值。

    - spec: JudgeSpec 对象，或直接传细则文本（此时按 1~100 分、min_score=60）。
    - min_score: 覆盖 spec.min_score 的通过线。
    - question: 产生该回答的用户问题/输入。评判"准确性/相关性"时建议传上——
      裁判需要看到原题才能核对回答是否正确（例如数学题，否则它无法判断 "391" 对不对）。
    """
    from ..judge.evaluator import llm_judge

    if isinstance(spec, str):
        spec = JudgeSpec(name="custom", criteria=spec)
    result = llm_judge(response, spec, client=client, context=context, question=question)
    threshold = min_score if min_score is not None else spec.min_score
    passed = result.score >= threshold
    message = (
        f"LLM-as-Judge [{spec.name}] {result.score:.1f}/{result.max_score:.0f} 分"
        f"（阈值 {threshold:.1f}）→ {'通过' if passed else '未达标'}\n"
        f"理由: {result.reasoning}\n回答: {response[:200]}"
    )
    tracker.add_assertion(
        f"assert_llm_judge[{spec.name}]", passed, message, result.score, threshold
    )
    if not passed:
        raise AssertionError(message)
    return result
