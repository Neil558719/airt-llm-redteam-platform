"""聊天机器人示例测试（Mock 与真实模型双模式）。

- `pytest tests/` → 被测 = mock-cs（Mock），裁判 = Mock，确定性、无需 API key；
- `pytest tests/ --app-model <模型> --app-api-key ...` → 被测 = 真实模型，裁判 = 配置的裁判模型。

真实模式下：`assert_similarity` 需要网关提供 Embedding 接口（如 text-embedding-3-small），
否则该条会报"异常/错误"（其余用例不受影响）。
"""

import pytest

from llmtest import (
    JudgeSpec,
    assert_json_schema,
    assert_llm_judge,
    assert_semantic_match,
    assert_similarity,
    assert_valid_json,
)

RAG_JSON_SCHEMA = {
    "type": "object",
    "required": ["name", "category", "features"],
    "properties": {
        "name": {"type": "string"},
        "category": {"type": "string"},
        "features": {"type": "array", "items": {"type": "string"}, "minItems": 2},
    },
    "additionalProperties": False,
}


def test_answer_semantically_matches_expected(app_under_test, llm_client):
    """语义断言：回答的含义应与期望一致（换述也算等价）。"""
    result = app_under_test.ask("用一句话解释什么是 RAG？")
    assert_semantic_match(
        result.answer,
        "检索增强生成，结合检索与生成",
        client=llm_client,
        threshold=0.6,
    )


def test_answer_similar_to_reference(app_under_test, llm_client):
    """相似度断言：回答与参考文本的向量余弦相似度达标。

    Mock 模式用确定性伪向量，总能测；真实模式下若网关没有 embedding 模型，
    框架会自动跳过该断言（pytest.skip），不会导致用例失败。
    """
    result = app_under_test.ask("介绍一下你自己")
    assert_similarity(
        result.answer,
        "AI 助手，解答问题，处理任务",
        client=llm_client,
        threshold=0.35,
    )


def test_returns_valid_json(app_under_test):
    """JSON 断言：回答必须是合法 JSON（自动兼容 ```json 代码块）。"""
    result = app_under_test.ask(
        "请只返回一个 JSON 对象：字段 name、category、features（字符串数组，至少 2 项），"
        "不要输出其它内容。"
    )
    assert_valid_json(result.answer)


def test_json_matches_schema(app_under_test):
    """Schema 校验：结构化输出必须符合约定 schema。"""
    result = app_under_test.ask(
        "请只返回一个 JSON 对象，只包含 name、category、features 三个字段"
        "（features 为字符串数组，至少 2 项），不要添加其它字段。"
    )
    data = assert_valid_json(result.answer)
    assert_json_schema(data, RAG_JSON_SCHEMA)


def test_greeting_quality_by_judge(app_under_test, llm_client):
    """LLM-as-Judge：按细则给回答打分并断言达标（传原题 question 便于裁判评估）。"""
    result = app_under_test.ask("你好")
    assert_llm_judge(
        result.answer,
        JudgeSpec.helpfulness(keywords=("智能助手", "为你服务", "解答问题")),
        question="你好",
        min_score=60,
        client=llm_client,
    )


@pytest.mark.parametrize("question,expected_keyword", [
    ("什么是 RAG？", "RAG"),
    ("1 + 1 等于几？", "2"),
])
def test_answer_contains_keyword(app_under_test, question, expected_keyword):
    """普通 pytest 断言也完全支持，框架不限制写法。"""
    result = app_under_test.ask(question)
    assert expected_keyword in result.answer
