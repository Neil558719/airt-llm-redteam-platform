"""OpenAIClient —— OpenAI 兼容客户端。

通过 `base_url` 可切换到 DeepSeek / 通义千问 / Moonshot / vLLM 等任何
OpenAI 兼容接口。SDK 懒加载，Mock 模式不需要安装。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..specs import (
    CONTRADICTED,
    NOT_SUPPORTED,
    SUPPORTED,
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
)
from ..utils import cosine_similarity
from .base import LLMClient, extract_json
from . import prompts

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIClient(LLMClient):
    provider = "openai"
    name = "openai"

    def __init__(self, config):
        super().__init__(config)
        self._client: Any = None

    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "真实模式需要 openai SDK，请安装：pip install llmtest[real]"
                ) from exc
            kwargs: Dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        client = self._get_client()
        params: Dict[str, Any] = {
            "model": self.config.model or DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            params["max_tokens"] = max_tokens
        # 网关 5xx / 429 / 断连等瞬时错误自动重试
        resp = self._retry_call(lambda: client.chat.completions.create(**params))
        content = resp.choices[0].message.content
        return content or ""

    def _embed(self, text: str) -> List[float]:
        client = self._get_client()
        model = self.config.embedding_model or DEFAULT_EMBEDDING_MODEL
        resp = self._retry_call(lambda: client.embeddings.create(model=model, input=text))
        return list(resp.data[0].embedding)

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> Any:
        # 语义等价优先用 LLM 判定（对换述/近义更稳健），失败回退向量余弦
        from ..specs import SemanticResult

        try:
            raw = self._llm_json(prompts.semantic_prompt(actual, expected, context))
            return SemanticResult(
                equivalent=bool(raw.get("equivalent", False)),
                score=float(raw.get("score", 0.0)),
                reasoning=str(raw.get("reasoning", "")),
            )
        except ValueError:
            a = self.embed(actual)
            b = self.embed(expected)
            score = cosine_similarity(a, b)
            return SemanticResult(
                equivalent=score >= 0.75,
                score=score,
                reasoning=f"LLM 判定失败，回退向量余弦 {score:.3f}（阈值 0.75）",
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
