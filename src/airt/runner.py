"""Asynchronous execution engine for multi-turn attack cases."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol, Sequence

from airt.adapter import RetryableTargetError, Target
from airt.models import (
    AttackCase,
    CaseResult,
    Message,
    Reply,
    ResultStatus,
    RunMetadata,
    Verdict,
)
from airt.evaluation_bridge import EvaluationContext
from airt.quality_bridge import QualityEvaluator


class Evaluator(Protocol):
    """Evaluate the final reply for one attack case."""

    async def evaluate(self, case: AttackCase, reply: Reply) -> Verdict:
        """Return a verdict for the target's final reply."""


EvaluatorLike = Evaluator | Callable[..., Awaitable[Verdict]]
QualityEvaluatorLike = Callable[[AttackCase, Reply, float], Any]


async def _chat_for_case(
    target: Target, case_id: str, messages: list[Message], *, case_input: dict[str, Any] | None = None
) -> Reply:
    """Use per-case target state when the optional capability is available."""

    case_chat = getattr(target, "chat_case", None)
    if case_chat is not None:
        try:
            return await case_chat(case_id, messages, case_input=case_input)
        except TypeError as error:
            if "case_input" not in str(error):
                raise
            return await case_chat(case_id, messages)
    return await target.chat(messages)


class _TokenBucket:
    """A small shared monotonic-time token bucket for request rate limiting."""

    def __init__(self, qps: float | None) -> None:
        self._qps = qps if qps is not None and qps > 0 else None
        self._capacity = max(1, math.ceil(self._qps)) if self._qps else 0
        self._tokens = float(self._capacity)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait for and consume one token, if rate limiting is enabled."""

        if self._qps is None:
            return

        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(
                    float(self._capacity), self._tokens + elapsed * self._qps
                )
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._qps
            await asyncio.sleep(wait)


async def _call_evaluator(
    evaluator: EvaluatorLike,
    case: AttackCase,
    reply: Reply,
    system_prompt: str,
) -> Verdict:
    """Call either an evaluator object or an async callable.

    The optional system prompt is forwarded only to evaluators that explicitly
    accept it, keeping the agreed two-argument evaluator contract intact.
    """

    function = getattr(evaluator, "evaluate", evaluator)
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "system_prompt" in parameters:
        value = function(case, reply, system_prompt=system_prompt)
    else:
        value = function(case, reply)
    if inspect.isawaitable(value):
        return await value
    return value


def _format_error(error: Exception) -> str:
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _read_completed(path: Path) -> set[str]:
    """Read completed IDs from an existing JSONL file without tolerating damage."""

    if not path.exists():
        return set()

    completed: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"could not read resume JSONL {path}: {error}") from error

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            result = CaseResult.model_validate_json(line)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(
                f"malformed JSONL at {path}:{line_number}"
            ) from error
        if result.status is ResultStatus.COMPLETED:
            completed.add(result.case_id)
    return completed


async def run_cases(
    cases: Sequence[AttackCase],
    target: Target,
    evaluator: EvaluatorLike,
    output_path: Path,
    *,
    concurrency: int,
    qps: float | None,
    retries: int,
    resume: bool = False,
    system_prompt: str = "",
    run_metadata: RunMetadata | None = None,
    quality_evaluator: QualityEvaluator | None = None,
    async_quality_evaluator: QualityEvaluatorLike | None = None,
) -> list[CaseResult]:
    """Run cases concurrently, persisting each result as soon as it finishes.

    ``retries`` is the number of retries after the initial request. Only
    :class:`RetryableTargetError` is retried. The rate limiter is shared by all
    workers and is acquired before every initial request and retry.
    """

    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    if retries < 0:
        raise ValueError("retries must be non-negative")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # A normal run is a fresh snapshot; resume deliberately preserves append semantics.
    if resume:
        completed_ids = _read_completed(output_path)
    else:
        try:
            output_path.write_text("", encoding="utf-8")
        except OSError as error:
            raise RuntimeError(f"could not initialize result JSONL {output_path}") from error
        completed_ids = set()
    pending = [case for case in cases if case.id not in completed_ids]
    write_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)
    limiter = _TokenBucket(qps)

    async def persist(result: CaseResult) -> None:
        line = result.model_dump_json()
        async with write_lock:
            try:
                with output_path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.write("\n")
                    stream.flush()
            except OSError as error:
                raise RuntimeError(f"could not write result JSONL {output_path}") from error

    async def execute(case: AttackCase) -> CaseResult:
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))

        final_reply: Reply | None = None
        error: Exception | None = None
        failure_kind: str | None = None
        stage = 'target'
        started: float | None = None
        target_latency_ms: float | None = None
        async with semaphore:
            # Measure the target interaction only. Queueing for another worker
            # and evaluator latency are harness overhead, not target latency.
            started = time.monotonic()
            try:
                for turn in case.turns:
                    messages.append(Message(role="user", content=turn))
                    for attempt in range(retries + 1):
                        await limiter.acquire()
                        try:
                            reply = await _chat_for_case(target, case.id, messages, case_input=case.input)
                        except RetryableTargetError as caught:
                            if attempt >= retries:
                                raise
                            await asyncio.sleep(0.25 * (2**attempt))
                        else:
                            final_reply = reply
                            messages.append(Message(role="assistant", content=reply.text))
                            break
            except Exception as caught:
                error = caught
                failure_kind = stage

            target_latency_ms = (time.monotonic() - started) * 1000
            if error is None:
                if final_reply is None:
                    error = RuntimeError("target returned no reply")
                else:
                    stage = 'judge'
                    try:
                        verdict = await _call_evaluator(
                            evaluator, case, final_reply, system_prompt
                        )
                    except Exception as caught:
                        error = caught
                        failure_kind = stage
                    else:
                        stage = 'quality'
                        quality_payload = (
                            await async_quality_evaluator(case, final_reply, target_latency_ms)
                            if async_quality_evaluator is not None
                            else quality_evaluator.evaluate(
                                EvaluationContext.from_reply(
                                    final_reply,
                                    latency_ms=target_latency_ms,
                                ),
                                expected_answer=case.quality.expected_answer,
                                semantic_threshold=case.quality.semantic_threshold,
                                max_hallucination_rate=case.quality.max_hallucination_rate,
                                json_schema=case.quality.json_schema,
                            ).as_dict()
                            if case.quality is not None and (quality_evaluator is not None or async_quality_evaluator is not None)
                            else None
                        )
                        result = CaseResult(
                            case_id=case.id,
                            case=case,
                            status=ResultStatus.COMPLETED,
                            run_metadata=run_metadata,
                            messages=messages,
                            reply=final_reply,
                            verdict=verdict,
                            latency_ms=target_latency_ms,
                            usage=final_reply.usage,
                            quality=quality_payload,
                            security_judge_used=getattr(verdict, "source", None) == "judge",
                            quality_judge_used=bool(quality_payload and quality_payload.get("judge_score") is not None),
                        )
                        await persist(result)
                        return result

            result = CaseResult(
                case_id=case.id,
                case=case,
                status=ResultStatus.ERROR,
                run_metadata=run_metadata,
                messages=messages,
                reply=final_reply,
                verdict=None,
                error=_format_error(error),
                latency_ms=target_latency_ms,
                usage=final_reply.usage if final_reply is not None else {},
                failure_kind=failure_kind or 'platform',
            )
            await persist(result)
            return result

    return await asyncio.gather(*(execute(case) for case in pending))





