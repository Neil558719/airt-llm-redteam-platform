"""Short-circuit orchestration for deterministic rules and an optional judge."""

from __future__ import annotations

from airt.judge.llm import Judge
from airt.judge.rules import rule_evaluate
from airt.models import AttackCase, JudgeMode, Reply, Verdict


async def evaluate(
    case: AttackCase,
    reply: Reply,
    *,
    system_prompt: str = "",
    judge: Judge | None = None,
    leak_ngram: int = 24,
    judge_mode_override: str | None = None,
) -> Verdict:
    """Evaluate a reply according to the case's configured judge mode.

    ``always`` delegates immediately.  ``auto`` uses a definite rule result
    when available and delegates only for ambiguous output.  ``never`` never
    makes a network call and records ambiguity as uncertain.
    """

    mode = case.detect.judge
    if judge_mode_override == "always":
        mode = JudgeMode.ALWAYS
    if mode is JudgeMode.ALWAYS:
        if judge is None:
            return Verdict(
                status="uncertain",
                source="judge",
                confidence=0.0,
                reason="judge is required by judge mode always but is not configured",
            )
        return await judge.judge(case, reply)

    ruled = rule_evaluate(case, reply, system_prompt, leak_ngram=leak_ngram)
    if ruled is not None:
        return ruled

    if mode is JudgeMode.AUTO and judge is not None:
        return await judge.judge(case, reply)

    return Verdict(
        status="uncertain",
        source="rule",
        confidence=0.0,
        reason=(
            "rules could not determine the verdict and no judge is configured"
            if judge is None
            else "judge mode never disables LLM judgment for ambiguous output"
        ),
    )
