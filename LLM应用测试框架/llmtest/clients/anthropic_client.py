"""AnthropicClient —— 调用 Claude 系列模型。

注意：Anthropic 没有原生 Embedding 接口，`embed()` 回退为确定性伪向量
（近似 token 覆盖），并在首次使用时打印警告；语义/Judge/幻觉判定走 LLM，不受影响。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ..specs import (
    CONTRADICTED,
    NOT_SUPPORTED,
    SUPPORTED,
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
    SemanticResult,
)
from ..utils import deterministic_embedding
from .base import LLMClient
from . import prompts

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicClient(LLMClient):
    provider = "anthropic"
    name = "anthropic"

    def __init__(self, config):
        super().__init__(config)
        self._client: Any = None
        self._embed_warned = False

    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "真实模式需要 anthropic SDK，请安装：pip install llmtest[real]"
                ) from exc
            kwargs: Dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = Anthropic(**kwargs)
        return self._client

    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        client = self._get_client()
        # anthropic API：system 提示单独传顶层参数
        system = None
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content")
            else:
                chat_messages.append(msg)
        params: Dict[str, Any] = {
            "model": self.config.model or DEFAULT_MODEL,
            "messages": chat_messages,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        # 网关 5xx / 429 / 断连等瞬时错误自动重试
        resp = self._retry_call(lambda: client.messages.create(**params))
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts)

    def _embed(self, text: str) -> List[float]:
        if not self._embed_warned:
            print(
                "警告: Anthropic 无原生 Embedding 接口，相似度计算回退为确定性伪向量"
                "（基于关键词覆盖，仅供近似）。需要精确向量请改用 OpenAI 兼容提供商。",
                file=sys.stderr,
            )
            self._embed_warned = True
        return deterministic_embedding(text)

    def embedding_available(self) -> bool:
        # Anthropic 无原生 embedding，但始终回退确定性伪向量，视为可用（避免探测触发警告）
        return True

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> SemanticResult:
        try:
            raw = self._llm_json(prompts.semantic_prompt(actual, expected, context))
            return SemanticResult(
                equivalent=bool(raw.get("equivalent", False)),
                score=float(raw.get("score", 0.0)),
                reasoning=str(raw.get("reasoning", "")),
            )
        except ValueError:
            from ..utils import cosine_similarity

            a = self.embed(actual)
            b = self.embed(expected)
            score = cosine_similarity(a, b)
            return SemanticResult(
                equivalent=score >= 0.75,
                score=score,
                reasoning=f"LLM 判定失败，回退伪向量余弦 {score:.3f}",
            )

    def _judge(
        self,
        response: str,
        spec: JudgeSpec,
        context: Optional[str] = None,
        question: Optional[str] = None,
    ) -> JudgeResult:
        raw = self._llm_json(
            prompts.judge_prompt(response, spec.criteria, spec.scale, context, question)
        )
        score = float(raw.get("score", 0.0))
        return JudgeResult(
            score=min(max(score, 1.0), float(spec.scale)),
            max_score=float(spec.scale),
            reasoning=str(raw.get("reasoning", "")),
            spec_name=spec.name,
        )

    def _extract_claims(self, text: str) -> List[str]:
        raw = self._llm_json(prompts.claim_extraction_prompt(text))
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return super()._extract_claims(text)

    def _verify_claim(self, claim: str, context: str) -> ClaimVerdict:
        raw = self._llm_json(prompts.claim_verify_prompt(claim, context))
        verdict = str(raw.get("verdict", NOT_SUPPORTED)).upper()
        if verdict not in (SUPPORTED, NOT_SUPPORTED, CONTRADICTED):
            verdict = NOT_SUPPORTED
        try:
            confidence = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        return ClaimVerdict(
            claim=claim,
            verdict=verdict,
            confidence=confidence,
            evidence=str(raw.get("evidence", "")),
        )
