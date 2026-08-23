"""多平台知识库客服批量问题集（数据驱动加载）。

问题数据从 data/knowledge_questions.json 读取（可维护、可版本化）：
  - core：语义断言核心题（test_kb_answers_from_knowledge_base 用）
  - bank：批量回归 / 双裁判对比（QUESTION_BANK）

口径与 knowledge_base.md 一致。注意控制题量：每题 = 被测平台调用 + 裁判调用，
真实模型单次几十秒。
"""

from __future__ import annotations

import json
import os
from typing import List, Tuple

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "knowledge_questions.json"
)


def load_questions() -> dict:
    """从 JSON 加载问题集，返回 {"core": [(q, exp)...], "bank": [(q, exp)...]}。"""
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "core": [(q["question"], q["expected"]) for q in data.get("core", [])],
        "bank": [(q["question"], q["expected"]) for q in data.get("bank", [])],
    }


QUESTION_BANK: List[Tuple[str, str]] = load_questions()["bank"]
