"""Chinese, human-readable presentation data for terminal and HTML reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from collections.abc import Sequence

from airt.models import CaseResult, RunMetadata

_LEGACY_METADATA = "Not recorded in original results (legacy JSONL)"

_CATEGORY_LABELS = {
    "prompt_injection": "提示注入",
    "indirect_injection": "间接提示注入",
    "jailbreak": "越狱",
    "roleplay": "角色扮演",
    "encoding_obfuscation": "编码混淆",
    "goal_hijacking": "目标劫持",
    "data_exfiltration": "数据外泄",
}
_SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
    "unknown": "未知",
}
_OUTCOME_LABELS = {
    "success": "攻击成功（存在安全风险）",
    "fail": "攻击未成功（模型保持边界）",
    "uncertain": "结论不确定（建议人工复核）",
    "error": "执行异常（未纳入攻击成功率）",
}
_SOURCE_LABELS = {"rule": "规则判定", "judge": "独立裁判模型"}
_ROLE_LABELS = {
    "user": "测试请求",
    "assistant": "对话上下文中的模型回复",
    "system": "系统提示",
}
_METADATA_LABELS = {
    "LLM red-team security assessment": "LLM 红队安全评估",
    "Automated API-based black-box testing": "基于 API 的自动化黑盒测试",
    _LEGACY_METADATA: "原始 JSONL 未记录（历史结果）",
}
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "credential",
    "cookie",
)


def _wire(value: object) -> str:
    return str(getattr(value, "value", value))


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Redact conventionally secret-bearing mapping values for display."""

    if isinstance(value, dict):
        return {
            str(key): "[已脱敏]" if _is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def category_label(value: object) -> str:
    wire = _wire(value)
    return _CATEGORY_LABELS.get(wire, wire)


def severity_label(value: object) -> str:
    wire = _wire(value)
    return _SEVERITY_LABELS.get(wire, wire)


def outcome_key(result: CaseResult) -> str:
    if _wire(result.status) == "error":
        return "error"
    return _wire(result.verdict.status) if result.verdict is not None else "uncertain"


def outcome_label(value: object) -> str:
    wire = _wire(value)
    return _OUTCOME_LABELS.get(wire, wire)


def source_label(value: object) -> str:
    wire = _wire(value)
    return _SOURCE_LABELS.get(wire, wire)


def metadata_label(value: str) -> str:
    return _METADATA_LABELS.get(value, value)


def metadata_display(metadata: RunMetadata, results: Sequence[CaseResult] | None = None) -> dict[str, str]:
    return {
        "test_type": metadata_label(metadata.test_type),
        "test_method": metadata_label(metadata.test_method),
        "target_profile": "Agent / 工具调用" if metadata.target_profile == "agent" else "纯文本对话",
        "run_mode": metadata.run_mode,
        "security_judge_policy": metadata.security_judge_policy,
        "quality_judge_mode": metadata.quality_judge_mode,
        "security_judge_used": "是" if any(item.security_judge_used for item in (results or [])) else "否",
        "quality_judge_used": "是" if any(item.quality_judge_used for item in (results or [])) else "否",
    }


def _safe_tool_value(value: Any) -> str:
    """Render tool evidence without exposing arbitrary nested protocol objects."""

    redacted = redact(value)
    if redacted is None:
        return "—"
    if isinstance(redacted, (dict, list)):
        import json

        return json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    return str(redacted)


def case_display(result: CaseResult) -> dict[str, Any]:
    """Build presentation-only fields without exposing adapter protocol payloads."""

    case = result.case
    last_assistant_index = max(
        (index for index, message in enumerate(result.messages) if message.role == "assistant"),
        default=-1,
    )
    context_messages = [
        {"label": _ROLE_LABELS[message.role], "content": redact(message.content)}
        for index, message in enumerate(result.messages)
        if message.role == "assistant" and index != last_assistant_index
    ]
    requests = [
        {"round": index, "content": redact(message.content)}
        for index, message in enumerate(
            (message for message in result.messages if message.role == "user"),
            start=1,
        )
    ]
    outcome = outcome_key(result)
    verdict: dict[str, str] | None = None
    if result.verdict is not None:
        verdict = {
            "outcome": outcome_label(outcome),
            "source": source_label(result.verdict.source),
            "confidence": f"{result.verdict.confidence * 100:.1f}%",
            "reason": str(redact((result.quality or {}).get("judge_reason") or result.verdict.reason))
            if result.quality is not None and (result.quality or {}).get("judge_reason")
            else str(redact(result.verdict.reason)),
        }

    tool_calls = [
        {
            "name": call.name,
            "provider": call.provider or "—",
            "status": call.status,
            "arguments": _safe_tool_value(call.arguments),
            "result": _safe_tool_value(call.result),
        }
        for call in (result.reply.tool_calls if result.reply is not None else [])
    ]

    return {
        "case_id": result.case_id,
        "name": case.name if case is not None else result.case_id,
        "category": category_label(case.category) if case is not None else "未知",
        "severity": severity_label(case.severity) if case is not None else "未知",
        "outcome": outcome,
        "outcome_label": outcome_label(outcome),
        "latency": f"{result.latency_ms:.1f} 毫秒" if result.latency_ms is not None else "—",
        "requests": requests,
        "context_messages": context_messages,
        "reply": str(redact(result.reply.text)) if result.reply is not None else "—",
        "tool_calls": tool_calls,
        "verdict": verdict,
        "error": str(redact(result.error)) if result.error else "",
    }


def case_displays(results: Sequence[CaseResult]) -> list[dict[str, Any]]:
    return [case_display(result) for result in results]
