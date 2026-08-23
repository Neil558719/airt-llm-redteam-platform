"""多平台知识库客服共享测试用例。

被测对象 = 知识库客服机器人（Dify 或 FastGPT，通过 --app 切换），
裁判 = 框架的 llm_client（--llm-*，独立模型），两者分离。

运行（PowerShell，在项目根目录；先设好对应平台的 FASTGPT_*/DIFY_* 环境变量）：
  pytest examples/kb_bots/ --app dify --llm-mode real --llm-provider openai --llm-model gpt-5.6-sol --llm-api-key sk-...
  pytest examples/kb_bots/ --app fastgpt --llm-mode real --llm-provider openai --llm-model gpt-5.6-sol --llm-api-key sk-...

同一套用例、同一个问题集，只换被测对象——两平台质量可直接对比。

覆盖 9 个评测维度：语义 / 换述 / 幻觉 / 拒答 / Judge 准确性 / Judge 相关性 /
JSON / 多轮 / 延迟，外加批量问题集回归。
"""

import pytest

from llmtest import (
    JudgeSpec,
    assert_hallucination_rate,
    assert_llm_judge,
    assert_semantic_match,
    assert_valid_json,
)

# 问题集从 data/knowledge_questions.json 加载（数据驱动，可维护、可版本化）
from question_bank import load_questions

KB_QUESTIONS = load_questions()["core"]


def _sources_text(result) -> str:
    """把被测平台检索到的知识片段拼成幻觉核对上下文。"""
    return "\n".join(result.sources)


def test_kb_answers_from_knowledge_base(app_under_test, llm_client):
    """语义断言：回答须符合知识库业务语义。"""
    for question, expected in KB_QUESTIONS:
        result = app_under_test.ask(question)
        assert result.answer, f"被测平台返回空回答：{question}"
        assert_semantic_match(
            result.answer, expected, client=llm_client, threshold=0.6
        )


def test_kb_answer_faithful_to_retrieved_sources(app_under_test, llm_client):
    """幻觉检测：回答必须忠于被测平台真实检索到的知识。

    核对对象是 result.sources —— 机器人生成时真正看到的检索结果。
    若平台未返回检索来源（如 FastGPT OpenAI 兼容接口不直接给引用）则跳过并给提示。
    """
    question = KB_QUESTIONS[0][0]
    result = app_under_test.ask(question)
    sources = _sources_text(result)
    if not sources:
        pytest.skip(
            "被测平台未返回检索来源（应用未启用知识库检索，或接口未返回引用）。"
            "幻觉检测无从核对，自动跳过；其余用例不受影响。"
        )
    assert_hallucination_rate(
        result.answer, sources, client=llm_client, max_rate=0.4
    )


def test_kb_quality_by_judge(app_under_test, llm_client):
    """LLM-as-Judge：按准确性细则打分（传原题 + 知识库 sources 作为 context）。"""
    question = KB_QUESTIONS[0][0]
    result = app_under_test.ask(question)
    assert_llm_judge(
        result.answer,
        JudgeSpec.accuracy(),
        question=question,
        context="\n".join(result.sources),
        min_score=60,
        client=llm_client,
    )


def test_kb_returns_valid_json(app_under_test):
    """JSON 断言：机器人能按要求输出结构化 JSON（自动兼容 ```json 代码块）。"""
    result = app_under_test.ask(
        "请只返回一个 JSON 对象：字段 name、category、features（字符串数组，至少 2 项），"
        "不要输出其它内容。"
    )
    assert_valid_json(result.answer)


def test_kb_latency_recorded(app_under_test):
    """延迟自动采集（看板「平均延迟」数据来源）。"""
    result = app_under_test.ask("你好")
    assert result.answer


def test_kb_robust_to_paraphrased_questions(app_under_test, llm_client):
    """换述提问鲁棒性：同一事实换种问法，机器人应仍能答出。"""
    result = app_under_test.ask("退货有没有时间限制？")
    assert result.answer
    assert_semantic_match(
        result.answer,
        "普通商品 7 天内可无理由退货，质量问题 15 天内可退换",
        client=llm_client,
        threshold=0.6,
    )


def test_kb_handles_out_of_knowledge(app_under_test, llm_client):
    """知识库外的问题：不得编造，应如实表示没有相关信息。"""
    result = app_under_test.ask("公司团建经费怎么申请？")  # 知识库没有的主题
    assert result.answer
    assert_semantic_match(
        result.answer,
        "知识库中没有相关信息，无法回答",
        client=llm_client,
        threshold=0.5,
    )


def test_kb_answer_relevant_by_judge(app_under_test, llm_client):
    """相关性 Judge：回答须紧扣所问问题，不能答非所问（传 sources 作为 context）。"""
    question = "退货需要满足什么条件？"
    result = app_under_test.ask(question)
    assert_llm_judge(
        result.answer,
        JudgeSpec.relevance(),
        question=question,
        context="\n".join(result.sources),
        min_score=60,
        client=llm_client,
    )


def test_kb_conversation_follow_up(app_under_test, llm_client):
    """多轮会话：追问"那运费呢"要能承接上文（退货话题），而非答非所问。"""
    first = app_under_test.ask("退货期限是几天？")
    assert first.answer
    follow = app_under_test.ask(
        "那运费谁出呢？",
        conversation_id=app_under_test.last_conversation_id,
    )
    assert follow.answer
    assert_semantic_match(
        follow.answer,
        "退货运费：非质量问题由买家承担，质量问题由商家承担",
        client=llm_client,
        threshold=0.6,
    )


def test_kb_question_bank_regression(app_under_test, llm_client):
    """批量问题集回归：一篮子常见问题整体通过率须达标（≥ 80%）。"""
    from question_bank import QUESTION_BANK
    from llmtest import semantic_match

    failures = []
    for question, expected in QUESTION_BANK:
        result = app_under_test.ask(question)
        assert result.answer, f"被测平台返回空回答：{question}"
        # semantic_match 是测量函数（不接收 threshold），用返回的 score 自行判 0.6 阈值
        r = semantic_match(result.answer, expected, client=llm_client)
        if r.score < 0.6:
            failures.append(f"{question} → 分 {r.score:.2f}，理由：{r.reasoning}")
    rate = (len(QUESTION_BANK) - len(failures)) / len(QUESTION_BANK)
    assert rate >= 0.8, (
        f"问题集通过率 {rate:.0%} 低于 80%"
        f"（{len(failures)}/{len(QUESTION_BANK)} 未过）：\n" + "\n".join(failures)
    )
