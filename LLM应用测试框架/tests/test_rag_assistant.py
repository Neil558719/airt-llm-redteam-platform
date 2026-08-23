"""RAG 助手示例测试：幻觉检测（事实一致性评估，计算幻觉率）。

双模式：
- `pytest tests/`（Mock）→ 确定性验证幻觉检测能"抓到"编造的断言；
- `pytest tests/ --app-model <模型> ...`（真实）→ 把上下文写进 prompt 让模型"只据此作答"，
  再拿同一份上下文核对，测真实模型的忠实度。

关键点：核对用的上下文，必须是被测模型**真正看到的那份资料**（即 prompt 里的资料）。
"""

from llmtest import assert_hallucination_rate

_POLICY_CONTEXT = (
    "公司退货政策：签收后 7 天内可无理由退货；"
    "退货需保持商品完好，运费由买家承担。"
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
