"""针对真实客服 App 的示例用例。

被测对象：你的客服 App（--app cs，通过 adapter 包成 ask()）。
裁判：框架的 llm_client（真实模式，独立模型）。
"""

from llmtest import (
    assert_hallucination_rate,
    assert_semantic_match,
    assert_valid_json,
)


def test_cs_answer_is_correct(app_under_test, llm_client):
    """语义断言：回答应告知发货时间与物流信息。"""
    result = app_under_test.ask("我的订单什么时候发货？")
    assert_semantic_match(
        result.answer,
        "告知发货时间与物流信息",
        client=llm_client,
        threshold=0.7,
    )


def test_cs_answer_faithful_to_policy(app_under_test, llm_client):
    """幻觉检测：回答必须忠于客服 App 自己返回的检索依据（citations）。"""
    result = app_under_test.ask("退货政策是什么？")
    assert_hallucination_rate(
        result.answer,
        result.sources,
        client=llm_client,
        max_rate=0.3,
    )


def test_cs_structured_output_is_json(app_under_test):
    """结构化输出：客服返回的 JSON 必须可解析。"""
    result = app_under_test.ask("用 JSON 返回我的订单状态")
    assert_valid_json(result.answer)
