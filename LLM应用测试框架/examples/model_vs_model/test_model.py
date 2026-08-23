"""模型对模型示例：被测模型（--app-model）vs 裁判模型（--llm-model）。

不需要真实 App，也不需要改任何代码——被测侧、裁判侧都从终端参数切换。

运行示例（在项目根目录）：
    pytest examples/model_vs_model/ \
        --app-provider deepseek --app-model deepseek-chat --app-api-key $DEEPSEEK_API_KEY \
        --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY

也支持纯环境变量方式（见 README.md）。
"""

from llmtest import (
    JudgeSpec,
    assert_hallucination_rate,
    assert_llm_judge,
    assert_semantic_match,
    assert_valid_json,
)

# 被测模型提示语里会带上这段上下文，并要求它只据此作答——幻觉检测用同一份核对。
_POLICY_CONTEXT = (
    "公司退货政策：签收后 7 天内可无理由退货；"
    "退货需保持商品完好，运费由买家承担。"
)


def _require_real(app_under_test, llm_client):
    """被测对象 / 裁判必须是真实模型；若是 Mock 兜底则跳过并给出可操作提示。"""
    import pytest

    if getattr(app_under_test, "is_mock", False):
        pytest.skip(
            "被测对象是 Mock（没跑到你配的模型）。"
            "请用 --app-model/--app-provider/--app-api-key 或环境变量 "
            "LLM_APP_MODEL/LLM_APP_PROVIDER/LLM_APP_API_KEY 指定被测模型。"
            "注意：PowerShell 的 $env: 只对当前窗口生效，换窗口/重启后需重新设置。"
        )
    if getattr(llm_client, "is_mock", False):
        pytest.skip(
            "裁判是 Mock（没跑到你配的裁判模型）。"
            "请用 --llm-mode real --llm-provider/--llm-model/--llm-api-key "
            "或环境变量 LLM_TEST_MODE/LLM_PROVIDER/LLM_MODEL/LLM_API_KEY 指定裁判。"
        )


def test_model_answers_from_context(app_under_test, llm_client):
    """被测模型须忠于 prompt 里的上下文作答（语义 + 幻觉检测）。"""
    _require_real(app_under_test, llm_client)
    question = (
        "请只根据以下资料回答问题，不要使用资料之外的信息。\n"
        f"资料：{_POLICY_CONTEXT}\n\n问：退货期限是几天？"
    )
    result = app_under_test.ask(question)

    # 期望只取问题真正问到的关键事实（"几天"），避免把未问到的条件也硬性要求
    assert_semantic_match(result.answer, "退货期限是7天", client=llm_client, threshold=0.6)
    # 回答必须忠于同一份上下文，不得编造
    assert_hallucination_rate(
        result.answer, _POLICY_CONTEXT, client=llm_client, max_rate=0.4
    )


def test_model_math_by_judge(app_under_test, llm_client):
    """数学题先做确定性校验（可靠），再演示 LLM-as-Judge 打分。"""
    _require_real(app_under_test, llm_client)
    question = "17 × 23 等于多少？"
    result = app_under_test.ask(question)
    # 数学有确定答案，用确定性断言保证正确（LLM 裁判可能对简洁数值答案过度解读）
    assert "391" in result.answer
    # 演示 LLM-as-Judge：传原题 question，裁判才能核对答案是否正确（简洁但正确不扣分）
    assert_llm_judge(
        result.answer,
        JudgeSpec.accuracy(keywords=("391",)),  # keywords 仅 Mock 模式使用
        question=question,
        min_score=60,
        client=llm_client,
    )


def test_model_returns_json(app_under_test):
    """被测模型输出结构化 JSON，须可解析（自动兼容 ```json 代码块）。"""
    _require_real(app_under_test, None)
    result = app_under_test.ask("用 JSON 输出你的名字和版本，字段为 name、version。")
    assert_valid_json(result.answer)
