"""MockLLMClient —— 确定性模拟客户端。

无需 API key、可离线运行，让框架在无网络/无费用环境下端到端跑通。
判定逻辑全部基于规则（关键词 / token 覆盖），结果确定、可复现。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..specs import (
    CONTRADICTED,
    NOT_SUPPORTED,
    SUPPORTED,
    AppResponse,
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
    SemanticResult,
)
from ..utils import (
    cosine_similarity,
    deterministic_embedding,
    token_containment,
    token_overlap_ratio,
)
from .base import LLMClient

_DEFAULT_REPLY = "这是 Mock 模式的默认回复。"

# 上下文支持率阈值
_SUPPORTED_MIN = 0.5
_CONTRADICT_MIN = 0.35
# 否定词（用于判定矛盾）
_NEGATION_WORDS = ("不", "并非", "没有", "未", "不能", "非")


class MockLLMClient(LLMClient):
    is_mock = True
    provider = "mock"
    name = "mock"

    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        user_msg = self._last_user_message(messages)
        self._simulate_latency()
        return self._answer_of(self._find_response(user_msg))

    def _ask(
        self,
        question: str,
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> AppResponse:
        self._simulate_latency()
        value = self._find_response(question)
        return AppResponse(answer=self._answer_of(value), sources=self._sources_of(value))

    # ------------------------------------------------------------------
    # 内部：响应匹配
    # ------------------------------------------------------------------

    @staticmethod
    def _last_user_message(messages: List[Dict[str, str]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

    def _simulate_latency(self) -> None:
        """模拟响应延迟（看板「平均延迟」演示用）。"""
        latency_ms = float(getattr(self.config, "mock_latency_ms", 8.0) or 0.0)
        if latency_ms > 0:
            time.sleep(latency_ms / 1000.0)

    def _find_response(self, prompt: str) -> Any:
        """按关键词匹配预设条目。

        mock_responses 的值可以是字符串，或 dict：{"answer": "...", "sources": [...]}。
        """
        responses = self.config.mock_responses or {}
        # 结构化列表形式：[{"match": "关键词", "response": ...}]
        if isinstance(responses, list):
            for entry in responses:
                match = str(entry.get("match", ""))
                if match and match in prompt:
                    return entry.get("response")
        # 字典形式：{关键词: 回答}
        else:
            for keyword, response in responses.items():
                if keyword != "default" and keyword and keyword in prompt:
                    return response
            if "default" in responses:
                return responses["default"]
        return _DEFAULT_REPLY

    @staticmethod
    def _answer_of(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("answer", ""))
        return str(value)

    @staticmethod
    def _sources_of(value: Any) -> List[str]:
        if isinstance(value, dict):
            return [str(s) for s in value.get("sources", [])]
        return []

    def _embed(self, text: str) -> List[float]:
        return deterministic_embedding(text)

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> SemanticResult:
        a = self.embed(actual)
        b = self.embed(expected)
        cosine = cosine_similarity(a, b)
        # 回答较长时余弦会被稀释，结合"期望含义包含度"取较优者
        containment = token_containment(expected, actual)
        score = max(cosine, containment)
        return SemanticResult(
            equivalent=score >= 0.7,
            score=score,
            reasoning=(
                f"Mock 语义判定：向量余弦 {cosine:.3f} / "
                f"期望包含度 {containment:.3f} → 取 {score:.3f}（阈值 0.7）"
            ),
        )

    def _judge(
        self,
        response: str,
        spec: JudgeSpec,
        context: Optional[str] = None,
        question: Optional[str] = None,
    ) -> JudgeResult:
        if spec.keywords:
            hits = [k for k in spec.keywords if k in response]
            ratio = len(hits) / len(spec.keywords)
            score = round(1.0 + (spec.scale - 1.0) * ratio, 2)
            missing = [k for k in spec.keywords if k not in response]
            reasoning = (
                f"Mock 打分：关键词命中 {len(hits)}/{len(spec.keywords)} "
                f"{hits}；缺失 {missing} → {score}/{spec.scale} 分"
            )
        else:
            score = float(spec.scale)
            reasoning = (
                f"Mock 打分：未配置关键词提示，按满分 {spec.scale} 处理；"
                "真实模式下会交给 LLM 按细则打分。"
            )
        return JudgeResult(
            score=score,
            max_score=float(spec.scale),
            reasoning=reasoning,
            spec_name=spec.name,
        )

    def _verify_claim(self, claim: str, context: str) -> ClaimVerdict:
        ratio = token_overlap_ratio(claim, context)
        has_negation = any(w in claim for w in _NEGATION_WORDS)
        if ratio >= _SUPPORTED_MIN:
            verdict, evidence = SUPPORTED, f"上下文 token 覆盖率 {ratio:.0%}"
        elif has_negation and ratio >= _CONTRADICT_MIN:
            verdict, evidence = (
                CONTRADICTED,
                f"断言含否定词且上下文覆盖率 {ratio:.0%}，与上下文冲突",
            )
        else:
            verdict, evidence = NOT_SUPPORTED, f"上下文 token 覆盖率 {ratio:.0%}，缺乏依据"
        return ClaimVerdict(claim=claim, verdict=verdict, evidence=evidence)
