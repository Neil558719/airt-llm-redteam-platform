"""相似度断言：基于文本向量余弦相似度。

框架级能力：若评测客户端没有可用的 Embedding 模型（如网关只开通了聊天模型），
`assert_similarity` 会自动跳过该断言（pytest.skip），而不是让用例失败；
`similarity` 测量函数则抛出 `EmbeddingUnavailableError` 以便上层感知。
"""

from __future__ import annotations

from typing import Optional

import pytest

from ..metrics.tracker import tracker
from ..registry import get_default_client
from ..utils import cosine_similarity


class EmbeddingUnavailableError(RuntimeError):
    """评测客户端没有可用的 Embedding 模型（网关未开通 embedding）。"""


def similarity(
    actual: str,
    expected: str,
    *,
    client=None,
) -> float:
    """测量两段文本的向量余弦相似度（0~1），并记录指标。

    Embedding 不可用时抛 EmbeddingUnavailableError。
    """
    client = client or get_default_client()
    if not client.embedding_available():
        raise EmbeddingUnavailableError(
            "评测客户端没有可用的 Embedding 模型（网关可能未开通 embedding），向量相似度无法计算"
        )
    score = cosine_similarity(client.embed(actual), client.embed(expected))
    tracker.record_metric("similarity_score", score)
    return score


def assert_similarity(
    actual: str,
    expected: str,
    *,
    client=None,
    threshold: float = 0.7,
) -> float:
    """断言相似度 ≥ threshold。失败抛 AssertionError。

    网关无 Embedding 模型时自动跳过该断言（pytest.skip），而不是让用例失败。
    """
    client = client or get_default_client()
    try:
        score = similarity(actual, expected, client=client)
    except EmbeddingUnavailableError as exc:
        pytest.skip(str(exc))
    passed = score >= threshold
    message = (
        f"相似度断言失败: 余弦相似度 {score:.3f} < 阈值 {threshold:.3f}\n"
        f"实际回答: {actual[:200]}\n期望文本: {expected[:200]}"
    )
    tracker.add_assertion("assert_similarity", passed, message, score, threshold)
    if not passed:
        raise AssertionError(message)
    return score
