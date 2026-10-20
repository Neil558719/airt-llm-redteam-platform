"""RAG 助手示例测试：幻觉检测（事实一致性评估，计算幻觉率）。

双模式：
- `pytest tests/`（Mock）→ 验证当前政策正例和独立数字事实反例；
- `pytest tests/ --app-model <模型> ...`（真实）→ 把上下文写进 prompt 让模型"只据此作答"，
  再拿同一份上下文核对，测真实模型的忠实度。

关键点：核对用的上下文，必须是被测模型**真正看到的那份资料**（即 prompt 里的资料）。
"""

import re

import pytest

from llmtest import assert_hallucination_rate, detect_hallucination
from llmtest.clients import get_client
from llmtest.config import Config

# 独立验收资料：与共享用例使用同一业务版本，但不导入 Mock 的回答作为参考。
_POLICY_CONTEXT = (
    "公司当前退货政策：未使用的标准商品，签收后 14 天内可按公开流程申请退货；"
    "定制商品、已拆封的个人护理商品与已完成的数字服务，不适用常规无理由退货；"
    "公开资料未明确退货运费承担方。"
)


def test_rag_answer_is_faithful_to_context(app_under_test, llm_client, record_metric):
    """RAG 回答不得虚构资料之外的事实（幻觉率 ≤ 阈值）。"""
    question = (
        "请只根据以下资料回答问题，不要使用资料之外的信息。\n"
        f"资料：{_POLICY_CONTEXT}\n\n问：退货期限是几天？"
    )
    result = app_under_test.ask(question)
    record_metric("retrieved_chunks", 3, unit="条")

    report = assert_hallucination_rate(
        result.answer,
        _POLICY_CONTEXT,
        client=llm_client,
        max_rate=0.4,
    )
    # 报告的幻觉率同时被自动记入指标，供看板聚合
    assert report.hallucination_rate <= 0.4


def test_rag_answer_fully_faithful_when_supported(app_under_test, llm_client):
    """当资料完整支撑回答时，幻觉率应接近 0。"""
    question = (
        "请只根据以下资料回答问题，不要使用资料之外的信息。\n"
        f"资料：{_POLICY_CONTEXT}\n\n问：退货需要满足什么条件？"
    )
    result = app_under_test.ask(question)
    assert_hallucination_rate(
        result.answer,
        _POLICY_CONTEXT,
        client=llm_client,
        max_rate=0.3,
    )


def test_rag_answer_latency_recorded(app_under_test):
    """响应延迟随 ask() 调用自动记录（看板「平均延迟」数据来源）。"""
    result = app_under_test.ask("什么是 RAG？")
    assert result.answer  # 非空即通过；延迟由框架自动采集


@pytest.mark.parametrize(
    "answer_window,policy_context",
    [
        pytest.param("7 天", _POLICY_CONTEXT, id="stale-7-day-answer"),
        pytest.param("9999 天", _POLICY_CONTEXT, id="fabricated-9999-day-answer"),
        pytest.param(
            "14 天", "历史政策：签收后 7 天内申请退货。", id="14-days-against-7-day-source"
        ),
    ],
)
def test_wrong_return_window_fails_hallucination_assertion(answer_window, policy_context):
    """仅验证最小数字事实；不代表近似全文的数值替换均能识别。"""
    reference_window = re.search(r"\d+ 天", policy_context).group()
    client = get_client(Config(mode="mock"))
    report = detect_hallucination(answer_window, reference_window, client=client)
    assert report.hallucination_rate == 1.0
    with pytest.raises(AssertionError):
        assert_hallucination_rate(
            answer_window, reference_window, client=client, max_rate=0.3
        )


def test_current_return_window_has_independent_policy_support():
    """14 天来自业务验收输入；参考仅从独立资料抽取，不从 Mock 回答生成。"""
    reference_window = re.search(r"\d+ 天", _POLICY_CONTEXT).group()
    report = assert_hallucination_rate(
        "14 天", reference_window, client=get_client(Config(mode="mock")), max_rate=0.3
    )
    assert report.hallucination_rate == 0.0
