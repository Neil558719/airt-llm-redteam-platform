"""工具函数：确定性伪向量、余弦相似度、分词、分句。

这些函数不依赖任何 LLM/第三方库，保证 Mock 模式下可离线、确定性运行。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Dict, List

# 中英文分句标点（句号/问号/感叹号/分号）
_SENTENCE_SPLIT_RE = re.compile(r"[。！？；!?;…]+\s*")
# 英文单词/数字
_EN_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
# 中文单字
_CN_CHAR_RE = re.compile(r"[一-鿿]")


def tokenize(text: str) -> List[str]:
    """切分 token：英文单词/数字整体，中文用滑动二元组（bigram）。

    bigram 比单字更有区分度：共享 bigram 越多，相似度越高；也更贴近词义，
    让 Mock 的相似度/幻觉判定更稳定。
    """
    tokens: List[str] = _EN_TOKEN_RE.findall(text.lower())
    cn_chars = _CN_CHAR_RE.findall(text)
    tokens.extend("".join(pair) for pair in zip(cn_chars, cn_chars[1:]))
    return tokens


def _hash_index(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim


def deterministic_embedding(text: str, dim: int = 256) -> List[float]:
    """把文本映射为确定性伪向量（词袋式 hash 向量）。

    共享 token 越多，余弦相似度越高，因此语义相近的文本分数更高。
    仅用于 Mock 模式/无 Embedding 接口时的回退，与真实 Embedding 维度一致。
    """
    vec: Dict[int, float] = {}
    for tok in tokenize(text):
        idx = _hash_index(tok, dim)
        vec[idx] = vec.get(idx, 0.0) + 1.0
    vec = {k: v for k, v in vec.items() if v != 0}
    return _densify(vec, dim)


def _densify(sparse: Dict[int, float], dim: int) -> List[float]:
    dense = [0.0] * dim
    for idx, val in sparse.items():
        dense[idx] = val
    return dense


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """两个向量的余弦相似度（纯 Python，无 numpy）。"""
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: {len(a)} vs {len(b)}")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def token_overlap_ratio(claim: str, context: str) -> float:
    """claim 中出现在 context 里的 token 占比（用于 Mock 事实核对）。"""
    claim_tokens = tokenize(claim)
    if not claim_tokens:
        return 0.0
    ctx_tokens = set(tokenize(context))
    hit = sum(1 for t in claim_tokens if t in ctx_tokens)
    return hit / len(claim_tokens)


def token_containment(needle_text: str, haystack_text: str) -> float:
    """needle 的 token 有多大比例出现在 haystack 中（0~1）。

    用于"期望含义包含在较长回答中"的语义判定：回答越长，余弦越被稀释，
    但包含度不受影响。
    """
    needle = set(tokenize(needle_text))
    if not needle:
        return 0.0
    haystack = set(tokenize(haystack_text))
    return len(needle & haystack) / len(needle)


def split_sentences(text: str) -> List[str]:
    """按中英文标点分句，保留非空句。"""
    parts = _SENTENCE_SPLIT_RE.split(text or "")
    return [p.strip() for p in parts if p and p.strip()]


def format_number(value: float | None, digits: int = 2, default: str = "—") -> str:
    """格式化数字，None 显示占位符。"""
    if value is None:
        return default
    return f"{value:.{digits}f}"


def fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms:.0f} ms"
