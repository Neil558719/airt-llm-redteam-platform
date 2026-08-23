"""Neutral response model shared by Airt and the quality test framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from airt.models import Reply, ToolCall


@dataclass(slots=True)
class EvaluationContext:
    """Provider-neutral result passed to quality, security, and stability evaluators."""

    answer: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    conversation_id: str | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_reply(
        cls,
        reply: Reply,
        *,
        conversation_id: str | None = None,
        latency_ms: float | None = None,
        sources: list[str] | None = None,
    ) -> "EvaluationContext":
        return cls(
            answer=reply.text,
            sources=list(reply.sources if sources is None else sources),
            tool_calls=list(reply.tool_calls),
            conversation_id=conversation_id,
            latency_ms=latency_ms,
            usage=dict(reply.usage),
            raw=dict(reply.raw or {}),
        )

    @classmethod
    def from_app_response(
        cls,
        response: Any,
        *,
        tool_calls: list[ToolCall] | None = None,
        conversation_id: str | None = None,
        latency_ms: float | None = None,
        usage: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> "EvaluationContext":
        answer = getattr(response, "answer", "")
        sources = getattr(response, "sources", [])
        if not isinstance(answer, str):
            answer = str(answer)
        if not isinstance(sources, list):
            sources = list(sources or [])
        return cls(
            answer=answer,
            sources=[str(source) for source in sources],
            tool_calls=list(tool_calls or []),
            conversation_id=conversation_id,
            latency_ms=latency_ms,
            usage=dict(usage or {}),
            raw=dict(raw or {}),
        )

    def to_app_response(self) -> Any:
        """Return llmtest.AppResponse when installed, otherwise a compatible fallback."""

        try:
            from llmtest.specs import AppResponse  # type: ignore[import-not-found]
        except ImportError:
            @dataclass
            class AppResponseFallback:
                answer: str = ""
                sources: list[str] = field(default_factory=list)

            return AppResponseFallback(answer=self.answer, sources=list(self.sources))
        return AppResponse(answer=self.answer, sources=list(self.sources))

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": list(self.sources),
            "tool_calls": [tool_call.model_dump(mode="json") for tool_call in self.tool_calls],
            "conversation_id": self.conversation_id,
            "latency_ms": self.latency_ms,
            "usage": dict(self.usage),
            "raw": dict(self.raw),
        }
