"""真实客户端的提示词模板。

所有模板要求 LLM 输出纯 JSON，客户端用 extract_json 稳健解析；
解析失败时调用方可重试一次。
"""

from __future__ import annotations

SEMANTIC_PROMPT = """你是语义等价性评判模型。判断下面两段文本是否"语义等价"（表达的含义相同，允许措辞不同）。
文本A（模型回答）：{actual}
文本B（期望含义）：{expected}
{context_note}只输出 JSON，格式：{{"equivalent": true 或 false, "score": 0.0 到 1.0 的小数, "reasoning": "一句话理由"}}
"""

JUDGE_PROMPT = """你是 LLM 评测打分模型。请严格按照下面细则，给"回答"在 1~{scale} 分之间打分（只能整数）。
打分细则：{criteria}
{question_note}{context_note}回答：{response}
只输出 JSON，格式：{{"score": 整数, "reasoning": "给出打分的简短理由"}}
"""

CLAIM_EXTRACTION_PROMPT = """把下面"回答"分解成若干条独立的事实断言（原子事实，一句话一条）。
回答：{response}
只输出 JSON 字符串数组，例如：["断言一", "断言二"]。不要输出任何其它内容。
"""

CLAIM_VERIFY_PROMPT = """你是事实一致性核对模型。判断"断言"是否被"上下文"支撑，还是矛盾，还是上下文未提及（无法证实）。
断言：{claim}
上下文：{context}
只输出 JSON，格式：{{"verdict": "SUPPORTED" 或 "NOT_SUPPORTED" 或 "CONTRADICTED", "confidence": 0.0 到 1.0 的小数, "evidence": "从上下文摘录的支撑/矛盾依据，若无则写空字符串"}}
"""


def _context_note(context: str | None) -> str:
    return f"参考上下文：{context}\n" if context else ""


def _question_note(question: str | None) -> str:
    return f"用户问题/输入：{question}\n" if question else ""


def semantic_prompt(actual: str, expected: str, context: str | None = None) -> str:
    return SEMANTIC_PROMPT.format(
        actual=actual, expected=expected, context_note=_context_note(context)
    )


def judge_prompt(
    response: str,
    criteria: str,
    scale: int,
    context: str | None = None,
    question: str | None = None,
) -> str:
    return JUDGE_PROMPT.format(
        response=response,
        criteria=criteria,
        scale=scale,
        question_note=_question_note(question),
        context_note=_context_note(context),
    )


def claim_extraction_prompt(response: str) -> str:
    return CLAIM_EXTRACTION_PROMPT.format(response=response)


def claim_verify_prompt(claim: str, context: str) -> str:
    return CLAIM_VERIFY_PROMPT.format(claim=claim, context=context)
