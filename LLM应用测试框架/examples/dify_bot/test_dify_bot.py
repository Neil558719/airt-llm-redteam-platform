"""Dify 客服机器人测试（知识库主题：退货 / 售后政策）。

被测对象 = Dify 上搭的客服机器人（知识库 RAG + 生成模型）；
裁判 = 框架的 llm_client（--llm-*，独立模型），两者分离。

运行（PowerShell，在项目根目录）：
  $env:DIFY_BASE_URL = "http://localhost/v1"            # 本地 Docker 部署
  $env:DIFY_API_KEY  = "app-xxx"                        # Dify 应用 API 密钥
  pytest examples/dify_bot/ --app dify --llm-mode real --llm-provider openai --llm-model gpt-5.6-sol --llm-api-key $env:DEEPSEEK_API_KEY

与 tests/ 里 10 个用例的对应关系（双模式→真实 Dify 的迁移示例）：
  - test_dify_answers_from_knowledge_base          → tests 用例 1（语义断言）
  - test_dify_answer_faithful_to_retrieved_sources → tests 用例 8/9（幻觉检测，
       但核对对象是 Dify 真实检索到的 sources，不是测试方编的资料——生产级做法）
  - test_dify_quality_by_judge                     → tests 用例 5（LLM-as-Judge，传原题）
  - test_dify_returns_valid_json                   → tests 用例 3/4（JSON / Schema）
  - test_dify_latency_recorded                     → tests 用例 10（延迟自动采集）
"""

import pytest

from llmtest import (
    JudgeSpec,
    assert_hallucination_rate,
    assert_llm_judge,
    assert_semantic_match,
    assert_valid_json,
)

# 问题 → 期望语义（"意思对"即可，别要求字面一致；按你实际知识库微调）
# 注意：期望要与知识库一致——普通商品 7 天、质量问题 15 天是分开的，
# 不要笼统写成"一律 7 天"，否则裁判会判语义不完全等价。
# 覆盖多主题（退货 / 运费 / 退款 / 发货 / 发票 / 积分），对应 knowledge_base.md。
KB_QUESTIONS = [
    ("退货期限是几天？", "普通商品 7 天内可无理由退货，质量问题商品 15 天内可退换"),
    ("退货需要满足什么条件？", "商品保持完好、配件齐全、未经损坏，且在退货期限内"),
    ("退货运费谁来承担？", "非质量问题买家承担，质量问题商家承担"),
    ("退款多久能到账？", "商家验收后一般 1 到 3 个工作日到账"),
    ("下单后一般多久发货？", "现货商品一般 48 小时内发货"),
    ("可以开发票吗？", "可以开具电子发票"),
    ("会员积分能干什么？", "积分可在下单时抵扣部分金额"),
]


def _sources_text(result) -> str:
    """把 Dify 检索到的知识片段拼成幻觉核对上下文。"""
    return "\n".join(result.sources)


def test_dify_answers_from_knowledge_base(app_under_test, llm_client):
    """语义断言：回答须符合知识库业务语义。"""
    for question, expected in KB_QUESTIONS:
        result = app_under_test.ask(question)
        assert result.answer, f"Dify 返回空回答：{question}"
        assert_semantic_match(
            result.answer, expected, client=llm_client, threshold=0.6
        )


def test_dify_answer_faithful_to_retrieved_sources(app_under_test, llm_client):
    """幻觉检测：回答必须忠于 Dify 真实检索到的知识（企业核心用例）。

    核对对象是 result.sources —— 机器人生成时真正看到的检索结果，
    而不是测试方另找的资料；Dify 应用若没挂知识库则跳过并给提示。
    """
    question = KB_QUESTIONS[0][0]
    result = app_under_test.ask(question)
    sources = _sources_text(result)
    if not sources:
        pytest.skip(
            "Dify 返回没有检索来源（应用未启用知识库检索，或未检索到内容）。"
            "请在 Dify 里给应用挂上知识库，并确认知识库索引已建好。"
        )
    assert_hallucination_rate(
        result.answer, sources, client=llm_client, max_rate=0.4
    )


def test_dify_quality_by_judge(app_under_test, llm_client):
    """LLM-as-Judge：按准确性细则打分。

    传原题（question）供裁判核对答案对不对；传 Dify 检索到的 sources 作为
    context，裁判还能核对回答是否有知识库依据、符合知识库口径。
    """
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


def test_dify_returns_valid_json(app_under_test):
    """JSON 断言：机器人能按要求输出结构化 JSON（自动兼容 ```json 代码块）。"""
    result = app_under_test.ask(
        "请只返回一个 JSON 对象：字段 name、category、features（字符串数组，至少 2 项），"
        "不要输出其它内容。"
    )
    assert_valid_json(result.answer)


def test_dify_latency_recorded(app_under_test):
    """延迟自动采集（看板「平均延迟」数据来源）。"""
    result = app_under_test.ask("你好")
    assert result.answer


def test_dify_robust_to_paraphrased_questions(app_under_test, llm_client):
    """换述提问鲁棒性：同一事实换种问法，机器人应仍能答出。

    语义断言的好处就在这——不要求字面一致，换个说法也能判"答对了"。
    """
    result = app_under_test.ask("退货有没有时间限制？")
    assert result.answer
    assert_semantic_match(
        result.answer,
        "普通商品 7 天内可无理由退货，质量问题 15 天内可退换",
        client=llm_client,
        threshold=0.6,
    )


def test_dify_handles_out_of_knowledge(app_under_test, llm_client):
    """知识库外的问题：不得编造，应如实表示没有相关信息。

    拒答是客服上线最需要守住的底线——宁可说不知道，不能一本正经地瞎编。
    真实模型措辞多变，阈值放低到 0.5 只判"是否表达了没有该信息"。
    """
    result = app_under_test.ask("公司团建经费怎么申请？")  # 知识库没有的主题
    assert result.answer
    assert_semantic_match(
        result.answer,
        "知识库中没有相关信息，无法回答",
        client=llm_client,
        threshold=0.5,
    )


def test_dify_answer_relevant_by_judge(app_under_test, llm_client):
    """相关性 Judge：回答须紧扣所问问题，不能答非所问。

    同时传 sources 作为 context，让裁判核对回答是否基于知识库、而非答非所问。
    """
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


def test_dify_conversation_follow_up(app_under_test, llm_client):
    """多轮会话：追问"那运费呢"要能承接上文（退货话题），而非答非所问。"""
    first = app_under_test.ask("退货期限是几天？")
    assert first.answer
    # 带上第一轮返回的会话 id，让 Dify 维持上下文
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


def test_dify_question_bank_regression(app_under_test, llm_client):
    """批量问题集回归：一篮子常见问题整体通过率须达标。

    比单点断言更接近真实回归——统计"多少比例的问题答对了"，
    个别问题措辞波动不影响整体判断（阈值 80%）。
    失败时列出每个未过的问题、分数与裁判理由，方便定位。
    """
    from question_bank import QUESTION_BANK
    from llmtest import semantic_match

    failures = []
    for question, expected in QUESTION_BANK:
        result = app_under_test.ask(question)
        assert result.answer, f"Dify 返回空回答：{question}"
        # semantic_match 是测量函数（不接收 threshold），用返回的 score 自行判 0.6 阈值
        r = semantic_match(result.answer, expected, client=llm_client)
        if r.score < 0.6:
            failures.append(f"{question} → 分 {r.score:.2f}，理由：{r.reasoning}")
    rate = (len(QUESTION_BANK) - len(failures)) / len(QUESTION_BANK)
    assert rate >= 0.8, (
        f"问题集通过率 {rate:.0%} 低于 80%"
        f"（{len(failures)}/{len(QUESTION_BANK)} 未过）：\n" + "\n".join(failures)
    )
