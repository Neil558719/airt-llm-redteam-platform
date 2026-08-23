"""LLMClient 抽象基类。

对外暴露的公开方法都经过计时包装（记录响应延迟），真正的实现在下划线方法里。
Mock 与真实客户端只需实现 `_*` 方法，公共行为（延迟采集、错误兜底）统一处理。
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from ..config import Config
from ..specs import (
    AppResponse,
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
    SemanticResult,
)
from ..utils import split_sentences

SOURCE_APP = "app"          # 被测应用的响应延迟（complete）
SOURCE_FRAMEWORK = "framework"  # 框架自身的评测调用


def extract_json(text: str) -> Any:
    """从 LLM 输出中稳健地提取第一个 JSON 对象或数组。"""
    if not text:
        raise ValueError("LLM 返回为空，无法解析 JSON")
    text = text.strip()
    # 直接是合法 JSON
    try:
        return _json_loads(text)
    except ValueError:
        pass
    # 去掉围栏代码块 ```json ... ```
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        try:
            return _json_loads(fenced.group(1))
        except ValueError:
            pass
    # 截取第一个 { } 或 [ ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return _json_loads(text[start : i + 1])
                    except ValueError:
                        break
    raise ValueError(f"无法从 LLM 输出解析 JSON:\n{text[:500]}")


def _json_loads(text: str):
    import json

    return json.loads(text)


class LLMClient(ABC):
    """所有 LLM 客户端（Mock / OpenAI 兼容 / Anthropic）的基类。"""

    is_mock = False
    provider = "base"
    name = "base"

    def __init__(self, config: Config):
        self.config = config
        self.last_latency_ms = 0.0

    # ------------------------------------------------------------------
    # 公开 API（含计时与指标采集）
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """聊天补全（被测应用 / 一般对话）。"""
        with self._timed(SOURCE_APP):
            return self._complete(messages, temperature=temperature, max_tokens=max_tokens)

    def ask(
        self,
        question: str,
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AppResponse:
        """向被测应用提问，返回结构化回答（answer + 检索来源 sources）。

        真实 RAG 应用应重写 `_ask` 携带其真实检索结果；默认实现仅返回 answer，sources 为空。
        """
        with self._timed(SOURCE_APP):
            return self._ask(question, temperature=temperature, max_tokens=max_tokens)

    def embed(self, text: str) -> List[float]:
        """文本向量。"""
        with self._timed(SOURCE_FRAMEWORK):
            return self._embed(text)

    def embedding_available(self) -> bool:
        """Embedding 接口是否可用（首次调用时探测一次并缓存）。

        网关未开通 embedding 模型（如 OpenAI 兼容网关只有聊天模型）时返回 False，
        供相似度断言等据此优雅跳过，而不是每次调用都抛错。
        """
        if not hasattr(self, "_embed_available"):
            try:
                self._embed("ping")
                self._embed_available = True
            except Exception:
                self._embed_available = False
        return self._embed_available

    def semantic_equivalent(
        self,
        actual: str,
        expected: str,
        context: Optional[str] = None,
    ) -> SemanticResult:
        """语义等价性评估。"""
        with self._timed(SOURCE_FRAMEWORK):
            return self._semantic_equivalent(actual, expected, context)

    def judge(
        self,
        response: str,
        spec: JudgeSpec,
        context: Optional[str] = None,
        question: Optional[str] = None,
    ) -> JudgeResult:
        """按细则对回答打分（LLM-as-Judge）。

        question 为产生该回答的用户问题/输入——评判"准确性/相关性"时裁判需要它才能核对，
        建议传上；纯质量维度（有用性等）可不传。
        """
        with self._timed(SOURCE_FRAMEWORK):
            return self._judge(response, spec, context, question)

    def extract_claims(self, text: str) -> List[str]:
        """把回答分解为事实断言列表。"""
        with self._timed(SOURCE_FRAMEWORK):
            return self._extract_claims(text)

    def verify_claim(self, claim: str, context: str) -> ClaimVerdict:
        """核对单条断言是否被上下文支撑。"""
        with self._timed(SOURCE_FRAMEWORK):
            return self._verify_claim(claim, context)

    # ------------------------------------------------------------------
    # 子类实现
    # ------------------------------------------------------------------

    @abstractmethod
    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str: ...

    @abstractmethod
    def _embed(self, text: str) -> List[float]: ...

    def _ask(
        self,
        question: str,
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> AppResponse:
        """默认实现：把问题当普通对话发出去，sources 为空。

        RAG 应用应重写此方法，把"检索 + 生成"用的同一份上下文放进 sources。
        """
        answer = self._complete(
            [{"role": "user", "content": question}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return AppResponse(answer=answer, sources=[])

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> SemanticResult:
        """默认实现：向量余弦相似度（子类可覆盖为 LLM 判定）。"""
        a = self.embed(actual)
        b = self.embed(expected)
        from ..utils import cosine_similarity

        score = cosine_similarity(a, b)
        return SemanticResult(
            equivalent=score >= 0.75,
            score=score,
            reasoning="基于向量余弦相似度（阈值 0.75）",
        )

    @abstractmethod
    def _judge(
        self,
        response: str,
        spec: JudgeSpec,
        context: Optional[str] = None,
        question: Optional[str] = None,
    ) -> JudgeResult: ...

    def _extract_claims(self, text: str) -> List[str]:
        """默认实现：按标点分句。"""
        return split_sentences(text)

    @abstractmethod
    def _verify_claim(self, claim: str, context: str) -> ClaimVerdict: ...

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _is_transient(exc: BaseException) -> bool:
        """判断是否属于"重试可能成功"的瞬时错误：5xx / 429 / 连接与超时。"""
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status in (429, 500, 502, 503, 504)
        name = type(exc).__name__
        if name in (
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
            "APIConnectionError",
            "ConnectionError",
            "TimeoutError",
            "RemoteProtocolError",
        ):
            return True
        return isinstance(exc, (ConnectionError, TimeoutError, OSError))

    def _retry_call(self, fn, *, retries: int = 2, base_delay: float = 0.6):
        """对 LLM 调用做瞬时错误重试（网关 5xx / 429 / 断连/超时），指数退避。"""
        last_exc: Optional[BaseException] = None
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self._is_transient(exc) or attempt >= retries:
                    raise
                time.sleep(base_delay * (attempt + 1))
        raise last_exc  # pragma: no cover

    @contextmanager
    def _timed(self, source: str):
        """计时上下文：记录本次调用的延迟并写入指标采集（用例内才记录）。"""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            self.last_latency_ms = ms
            try:
                from ..metrics.tracker import tracker

                tracker.record_latency(ms, source)
            except Exception:
                pass

    def _llm_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        retries: int = 1,
        temperature: float = 0.0,
    ) -> Any:
        """调用 LLM 并要求输出 JSON，解析失败自动重试。直接走 _complete，避免重复计时。"""
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        last_err: Optional[Exception] = None
        for _ in range(retries + 1):
            try:
                raw = self._complete(messages, temperature=temperature, max_tokens=None)
                return extract_json(raw)
            except ValueError as exc:
                last_err = exc
        raise ValueError(f"LLM JSON 解析失败（已重试 {retries} 次）：{last_err}")
