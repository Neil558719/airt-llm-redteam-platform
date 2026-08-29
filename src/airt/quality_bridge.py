"""Offline quality evaluation facade for Airt responses.

The facade mirrors the useful, data-oriented parts of ``llmtest`` while
keeping Airt independently installable. A future live Judge can be injected
through ``semantic_fn`` or ``hallucination_fn`` without changing callers.
"""

from __future__ import annotations

import json
import httpx
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from airt.evaluation_bridge import EvaluationContext


def _tokens(text: str) -> set[str]:
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    words = {word.lower() for word in text.replace("，", " ").replace("。", " ").split() if word}
    words.update("".join(pair) for pair in zip(chars, chars[1:]))
    return words


def _semantic_score(actual: str, expected: str) -> float:
    expected_tokens = _tokens(expected)
    actual_tokens = _tokens(actual)
    if not expected_tokens:
        return 1.0 if not actual_tokens else 0.0
    return len(expected_tokens & actual_tokens) / len(expected_tokens)


_UNCERTAINTY_MARKERS = (
    "无法确定",
    "无法从",
    "未明确",
    "未说明",
    "没有相关资料",
    "信息不足",
    "不确定",
    "可能因",
    "以订单页面",
    "建议联系",
    "建议顾客",
)


def _numeric_tokens(text: str) -> list[str]:
    # Markdown list markers and document identifiers are not business facts.
    normalized = re.sub(r"(?m)^\s*\d+\s*[.)、]\s*", "", text)
    values: list[str] = []
    for match in re.finditer(r"\d+(?:\.\d+)?|[零一二三四五六七八九十百千万亿]+", normalized):
        before = next((char for char in reversed(normalized[:match.start()]) if not char.isspace()), "")
        after = next((char for char in normalized[match.end():] if not char.isspace()), "")
        if before in "-_/." or after in "-_/.:":
            continue
        if not ("\u4e00" <= before <= "\u9fff" or "\u4e00" <= after <= "\u9fff"):
            continue
        values.append(match.group())
    return values


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _sentence_is_supported(sentence: str, source_text: str) -> bool:
    """Use conservative evidence matching for paraphrased RAG answers."""

    sentence = sentence.strip()
    source_text = source_text.strip()
    if not sentence or not source_text:
        return False if sentence else True
    compact_sentence = _compact(sentence)
    compact_source = _compact(source_text)
    if any(marker in compact_sentence for marker in _UNCERTAINTY_MARKERS):
        return True

    # Numeric facts are only supported when the exact value is present in the
    # retrieved evidence; this keeps concise paraphrases safe without allowing
    # a changed deadline or quantity through lexical similarity.
    numbers = _numeric_tokens(compact_sentence)
    if numbers and any(number not in compact_source for number in numbers):
        return False

    if compact_sentence in compact_source:
        return True
    sentence_tokens = _tokens(sentence)
    source_tokens = _tokens(source_text)
    if not sentence_tokens:
        return True
    overlap = len(sentence_tokens & source_tokens) / len(sentence_tokens)
    if overlap >= 0.35:
        return True
    if numbers:
        meaningful = [token for token in sentence_tokens if len(token) >= 2 or token.isdigit()]
        return any(token in source_tokens for token in meaningful)
    return False


def _schema_error(value: Any, schema: dict[str, Any], path: str = "$") -> str | None:
    expected_type = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected_type in type_ok and not type_ok[expected_type]:
        return f"{path}: expected {expected_type}"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"{path}.{key}: required property missing"
        for key, child in schema.get("properties", {}).items():
            if key in value and isinstance(child, dict):
                error = _schema_error(value[key], child, f"{path}.{key}")
                if error:
                    return error
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            error = _schema_error(item, schema["items"], f"{path}[{index}]")
            if error:
                return error
    return None


@dataclass(slots=True)
class QualityResult:
    semantic_score: float | None = None
    semantic_passed: bool | None = None
    hallucination_rate: float | None = None
    hallucination_passed: bool | None = None
    json_valid: bool | None = None
    schema_valid: bool | None = None
    schema_error: str | None = None
    latency_ms: float | None = None
    errors: list[str] = field(default_factory=list)
    judge_score: float | None = None
    judge_passed: bool | None = None
    judge_reason: str | None = None
    judge_latency_ms: float | None = None
    judge_usage: dict[str, Any] = field(default_factory=dict)
    judge_cost: float | None = None

    @property
    def passed(self) -> bool:
        checks = [self.semantic_passed, self.hallucination_passed, self.schema_valid]
        checks.extend([self.json_valid] if self.json_valid is not None else [])
        return not self.errors and all(value is not False for value in checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantic_score": self.semantic_score,
            "semantic_passed": self.semantic_passed,
            "hallucination_rate": self.hallucination_rate,
            "hallucination_passed": self.hallucination_passed,
            "json_valid": self.json_valid,
            "schema_valid": self.schema_valid,
            "schema_error": self.schema_error,
            "latency_ms": self.latency_ms,
            "passed": self.passed,
            "errors": list(self.errors),
            "judge_score": self.judge_score,
            "judge_passed": self.judge_passed,
            "judge_reason": self.judge_reason,
            "judge_latency_ms": self.judge_latency_ms,
            "judge_usage": dict(self.judge_usage),
            "judge_cost": self.judge_cost,
        }


@dataclass(slots=True)
class QualitySummary:
    """Aggregated quality dimensions for JSON/HTML reports."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    semantic_score: float | None = None
    hallucination_rate: float | None = None
    average_latency_ms: float | None = None
    average_judge_latency_ms: float | None = None
    total_judge_cost: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None

    @staticmethod
    def _percentile(values: list[float], percent: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = (len(ordered) - 1) * percent
        lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    @classmethod
    def from_results(cls, results: list[QualityResult]) -> "QualitySummary":
        if not results:
            return cls()
        semantic = [item.semantic_score for item in results if item.semantic_score is not None]
        hallucination = [item.hallucination_rate for item in results if item.hallucination_rate is not None]
        latency = [item.latency_ms for item in results if item.latency_ms is not None]
        judge_latency = [item.judge_latency_ms for item in results if item.judge_latency_ms is not None]
        judge_cost = [item.judge_cost for item in results if item.judge_cost is not None]
        passed = sum(item.passed for item in results)
        return cls(total=len(results), passed=passed, failed=len(results) - passed,
                   semantic_score=(sum(semantic) / len(semantic)) if semantic else None,
                   hallucination_rate=(sum(hallucination) / len(hallucination)) if hallucination else None,
                   average_latency_ms=(sum(latency) / len(latency)) if latency else None,
                   average_judge_latency_ms=(sum(judge_latency) / len(judge_latency)) if judge_latency else None,
                   total_judge_cost=sum(judge_cost) if judge_cost else None,
                   latency_p50_ms=cls._percentile(latency, .50),
                   latency_p95_ms=cls._percentile(latency, .95),
                   latency_p99_ms=cls._percentile(latency, .99))

    @classmethod
    def from_dicts(cls, values: list[dict[str, Any]]) -> "QualitySummary":
        items = [QualityResult(
            semantic_score=value.get("semantic_score"),
            semantic_passed=value.get("semantic_passed"),
            hallucination_rate=value.get("hallucination_rate"),
            hallucination_passed=value.get("hallucination_passed"),
            json_valid=value.get("json_valid"),
            schema_valid=value.get("schema_valid"),
            schema_error=value.get("schema_error"),
            latency_ms=value.get("latency_ms"),
            errors=list(value.get("errors") or []),
            judge_score=value.get("judge_score"),
            judge_passed=value.get("judge_passed"),
            judge_reason=value.get("judge_reason"),
            judge_latency_ms=value.get("judge_latency_ms"),
            judge_usage=dict(value.get("judge_usage") or {}),
            judge_cost=value.get("judge_cost"),
        ) for value in values]
        return cls.from_results(items)

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "passed": self.passed, "failed": self.failed,
                "pass_rate": self.passed / self.total if self.total else 0.0,
                "semantic_score": self.semantic_score, "hallucination_rate": self.hallucination_rate,
                "average_latency_ms": self.average_latency_ms,
                "average_judge_latency_ms": self.average_judge_latency_ms,
                "total_judge_cost": self.total_judge_cost,
                "latency_p50_ms": self.latency_p50_ms,
                "latency_p95_ms": self.latency_p95_ms,
                "latency_p99_ms": self.latency_p99_ms}


@dataclass(slots=True)
class QualityJudgeResult:
    score: float
    reason: str
    threshold: float = 0.7
    latency_ms: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


class LiveQualityJudge:
    """OpenAI-compatible independent judge for quality rubrics."""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 60.0, threshold: float = 0.7, prompt_price_per_1k: float | None = None, completion_price_per_1k: float | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._threshold = threshold
        self._prompt_price = prompt_price_per_1k
        self._completion_price = completion_price_per_1k
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"

    async def evaluate(self, question: str, answer: str, rubric: str, *, context: str = "") -> QualityJudgeResult:
        prompt = (
            "你是独立的质量评测裁判。只返回 JSON：{\"score\": 0到1之间的小数, \"reason\": \"简短中文理由\"}。\n"
            f"评分标准：{rubric}\n问题：<question>{question}</question>\n"
            f"回答：<answer>{answer}</answer>\n上下文：<context>{context}</context>"
        )
        started = time.perf_counter()
        response = await self._client.post(self._endpoint, headers={"Authorization": f"Bearer {self._api_key}"}, json={"model": self._model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "response_format": {"type": "json_object"}})
        latency_ms = (time.perf_counter() - started) * 1000
        if response.is_error:
            raise RuntimeError(f"quality judge returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            score = float(data["score"])
            reason = str(data["reason"])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("quality judge response is malformed") from error
        if not 0.0 <= score <= 1.0 or not reason:
            raise RuntimeError("quality judge response is outside the supported range")
        usage = response.json().get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        cost = None
        if self._prompt_price is not None or self._completion_price is not None:
            cost = (float(usage.get("prompt_tokens", 0)) / 1000 * (self._prompt_price or 0)) + (float(usage.get("completion_tokens", 0)) / 1000 * (self._completion_price or 0))
        return QualityJudgeResult(score=score, reason=reason, threshold=self._threshold, latency_ms=latency_ms, usage=usage, cost=cost)

    async def aclose(self) -> None:
        await self._client.aclose()


class QualityEvaluator:
    """Evaluate one normalized response using deterministic offline checks."""

    def __init__(
        self,
        *,
        semantic_fn: Callable[[str, str], float] | None = None,
        hallucination_fn: Callable[[str, list[str]], float] | None = None,
    ) -> None:
        self._semantic_fn = semantic_fn or _semantic_score
        self._hallucination_fn = hallucination_fn

    def evaluate(
        self,
        context: EvaluationContext,
        *,
        expected_answer: str | None = None,
        semantic_threshold: float = 0.7,
        max_hallucination_rate: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> QualityResult:
        result = QualityResult(latency_ms=context.latency_ms)
        if expected_answer is not None:
            result.semantic_score = round(self._semantic_fn(context.answer, expected_answer), 6)
            result.semantic_passed = result.semantic_score >= semantic_threshold
            if not result.semantic_passed:
                result.errors.append(f"semantic score {result.semantic_score:.3f} < {semantic_threshold:.3f}")
        if max_hallucination_rate is not None:
            if self._hallucination_fn is not None:
                rate = self._hallucination_fn(context.answer, context.sources)
            else:
                source_text = "\n".join(context.sources)
                sentences = [part.strip() for part in context.answer.replace("！", "。").split("。") if part.strip()]
                unsupported = sum(1 for sentence in sentences if not _sentence_is_supported(sentence, source_text))
                rate = unsupported / len(sentences) if sentences else 0.0
            result.hallucination_rate = round(rate, 6)
            result.hallucination_passed = rate <= max_hallucination_rate
            if not result.hallucination_passed:
                result.errors.append(f"hallucination rate {rate:.3f} > {max_hallucination_rate:.3f}")
        if json_schema is not None:
            try:
                data = json.loads(context.answer)
                result.json_valid = True
            except (TypeError, json.JSONDecodeError) as error:
                result.json_valid = False
                result.schema_valid = False
                result.schema_error = f"invalid JSON: {error}"
                result.errors.append(result.schema_error)
            else:
                result.schema_error = _schema_error(data, json_schema)
                result.schema_valid = result.schema_error is None
                if not result.schema_valid:
                    result.errors.append(result.schema_error or "schema validation failed")
        return result
