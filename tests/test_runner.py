import asyncio
import json
import time

import pytest

from airt.adapter import RetryableTargetError, TargetResponseError
from airt.models import AttackCase, Reply, Verdict
from airt.quality_bridge import QualityEvaluator
from airt.runner import run_cases


class FakeTarget:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []
        self.conversations = []

    async def chat(self, messages):
        self.conversations.append(list(messages))
        case_id = next(message.content for message in reversed(messages) if message.role == "user")
        self.calls.append(case_id)
        value = self.replies[case_id]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return Reply(text=value, usage={"reply_tokens": 1})


class FakeEvaluator:
    async def evaluate(self, case, reply):
        return Verdict(
            status="success" if "PASS" in reply.text else "fail",
            source="rule",
            confidence=1.0,
            reason="test",
        )


def make_case(case_id: str, *turns: str) -> AttackCase:
    return AttackCase(
        id=case_id,
        name=case_id,
        category="jailbreak",
        severity="high",
        turns=list(turns),
        detect={},
    )


@pytest.mark.asyncio
async def test_runner_persists_optional_quality_result(tmp_path):
    case = AttackCase(
        id="quality",
        name="quality",
        category="roleplay",
        severity="low",
        turns=["status"],
        quality={"expected_answer": "订单已发货", "semantic_threshold": 0.7},
    )
    target = FakeTarget({"status": "订单已发货"})

    results = await run_cases(
        [case], target, FakeEvaluator(), tmp_path / "results.jsonl",
        concurrency=1, qps=None, retries=0, quality_evaluator=QualityEvaluator(),
    )

    assert results[0].quality is not None
    assert results[0].quality["semantic_passed"] is True


@pytest.mark.asyncio
async def test_runner_writes_results_and_skips_completed_cases(tmp_path):
    cases = [make_case("a", "a"), make_case("b", "b")]
    path = tmp_path / "results.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "a",
                "status": "completed",
                "verdict": {
                    "status": "fail",
                    "source": "rule",
                    "confidence": 1.0,
                    "reason": "old",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    target = FakeTarget({"a": "PASS", "b": "PASS"})

    results = await run_cases(
        cases,
        target,
        FakeEvaluator(),
        path,
        concurrency=2,
        qps=None,
        retries=0,
        resume=True,
    )

    assert [result.case_id for result in results] == ["b"]
    assert target.calls == ["b"]
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[-1])["case_id"] == "b"


@pytest.mark.asyncio
async def test_transport_error_is_error_not_fail(tmp_path):
    case = make_case("a", "a")
    results = await run_cases(
        [case],
        FakeTarget({"a": TimeoutError("down")}),
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=1,
        qps=None,
        retries=1,
        resume=False,
    )

    assert results[0].status == "error"
    assert results[0].verdict is None
    assert results[0].error is not None


@pytest.mark.asyncio
async def test_only_retryable_target_errors_are_retried(tmp_path):
    target = FakeTarget(
        {"retry": [RetryableTargetError("temporary"), "PASS"], "bad": TargetResponseError("bad")}
    )
    results = await run_cases(
        [make_case("retry", "retry"), make_case("bad", "bad")],
        target,
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=1,
        qps=None,
        retries=1,
        resume=False,
    )

    assert [result.status for result in results] == ["completed", "error"]
    assert target.calls == ["retry", "retry", "bad"]


@pytest.mark.asyncio
async def test_multiturn_conversation_preserves_assistant_replies_and_system_prompt(tmp_path):
    target = FakeTarget({"first": "first reply", "second": "PASS final"})
    result = (
        await run_cases(
            [make_case("multi", "first", "second")],
            target,
            FakeEvaluator(),
            tmp_path / "results.jsonl",
            concurrency=1,
            qps=None,
            retries=0,
            resume=False,
            system_prompt="You are a safe assistant.",
        )
    )[0]

    assert result.status == "completed"
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message.content for message in result.messages] == [
        "You are a safe assistant.",
        "first",
        "first reply",
        "second",
        "PASS final",
    ]
    assert target.conversations[1][-1].content == "second"
    assert target.conversations[1][-2].content == "first reply"
    assert result.reply is not None and result.reply.text == "PASS final"


@pytest.mark.asyncio
async def test_case_aware_target_isolated_across_concurrent_multiturn_cases(tmp_path):
    class CaseAwareTarget:
        def __init__(self):
            self.calls = []
            self.conversation_ids = {}

        async def chat_case(self, case_id, messages):
            await asyncio.sleep(0)
            prior_id = self.conversation_ids.get(case_id)
            self.calls.append((case_id, list(messages), prior_id))
            conversation_id = f"conversation-{case_id}"
            self.conversation_ids[case_id] = conversation_id
            return Reply(
                text="PASS" if len([m for m in messages if m.role == "user"]) == 2 else "continue",
                raw={"conversation_id": conversation_id},
            )

    target = CaseAwareTarget()
    results = await run_cases(
        [make_case("case-a", "a-first", "a-second"), make_case("case-b", "b-first", "b-second")],
        target,
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=2,
        qps=None,
        retries=0,
        resume=False,
    )

    assert [result.status for result in results] == ["completed", "completed"]
    calls_by_case = {
        case_id: [call for call in target.calls if call[0] == case_id]
        for case_id in ("case-a", "case-b")
    }
    assert calls_by_case["case-a"][0][2] is None
    assert calls_by_case["case-a"][1][2] == "conversation-case-a"
    assert calls_by_case["case-b"][0][2] is None
    assert calls_by_case["case-b"][1][2] == "conversation-case-b"
    assert all(
        prior_id != "conversation-case-b" for _, _, prior_id in calls_by_case["case-a"]
    )
    assert all(
        prior_id != "conversation-case-a" for _, _, prior_id in calls_by_case["case-b"]
    )


@pytest.mark.asyncio
async def test_malformed_resume_jsonl_is_rejected(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text('{"case_id": "a"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSONL"):
        await run_cases(
            [make_case("a", "a")],
            FakeTarget({"a": "PASS"}),
            FakeEvaluator(),
            path,
            concurrency=1,
            qps=None,
            retries=0,
            resume=True,
        )


@pytest.mark.asyncio
async def test_qps_limiter_is_shared_by_workers(tmp_path):
    call_times = []

    class TimedTarget(FakeTarget):
        async def chat(self, messages):
            call_times.append(time.monotonic())
            return await super().chat(messages)

    target = TimedTarget({"a": "PASS", "b": "PASS"})
    results = await run_cases(
        [make_case("a", "a"), make_case("b", "b")],
        target,
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=2,
        qps=1,
        retries=0,
        resume=False,
    )

    assert [result.status for result in results] == ["completed", "completed"]
    assert len(target.calls) == 2
    assert call_times[1] - call_times[0] >= 0.9


@pytest.mark.asyncio
async def test_case_latency_excludes_waiting_for_another_case_slot(tmp_path):
    class FirstCaseSlowTarget(FakeTarget):
        async def chat(self, messages):
            case_id = next(message.content for message in reversed(messages) if message.role == "user")
            if case_id == "slow":
                await asyncio.sleep(0.15)
            return await super().chat(messages)

    target = FirstCaseSlowTarget({"slow": "PASS", "fast": "PASS"})
    results = await run_cases(
        [make_case("slow", "slow"), make_case("fast", "fast")],
        target,
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=1,
        qps=None,
        retries=0,
        resume=False,
    )

    assert results[1].latency_ms is not None
    assert results[0].latency_ms is not None
    assert results[1].latency_ms < results[0].latency_ms * 0.5


@pytest.mark.asyncio
async def test_case_latency_excludes_evaluator_time(tmp_path):
    class SlowEvaluator(FakeEvaluator):
        async def evaluate(self, case, reply):
            await asyncio.sleep(0.15)
            return await super().evaluate(case, reply)

    result = (
        await run_cases(
            [make_case("fast", "fast")],
            FakeTarget({"fast": "PASS"}),
            SlowEvaluator(),
            tmp_path / "results.jsonl",
            concurrency=1,
            qps=None,
            retries=0,
            resume=False,
        )
    )[0]

    assert result.latency_ms is not None
    assert result.latency_ms < 100


@pytest.mark.asyncio
async def test_concurrency_is_bounded_across_cases(tmp_path):
    class BlockingTarget(FakeTarget):
        def __init__(self):
            super().__init__({case_id: "PASS" for case_id in ("a", "b", "c")})
            self.active = 0
            self.maximum_active = 0

        async def chat(self, messages):
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            try:
                await asyncio.sleep(0.02)
                return await super().chat(messages)
            finally:
                self.active -= 1

    target = BlockingTarget()
    await run_cases(
        [make_case("a", "a"), make_case("b", "b"), make_case("c", "c")],
        target,
        FakeEvaluator(),
        tmp_path / "results.jsonl",
        concurrency=2,
        qps=None,
        retries=0,
        resume=False,
    )

    assert target.maximum_active == 2

@pytest.mark.asyncio
async def test_runner_classifies_target_failures(tmp_path):
    case = make_case("broken", "broken")
    target = FakeTarget({"broken": RuntimeError("target down")})
    results = await run_cases(
        [case], target, FakeEvaluator(), tmp_path / "results.jsonl",
        concurrency=1, qps=None, retries=0,
    )
    assert results[0].status.value == "error"
    assert results[0].failure_kind == "target"
