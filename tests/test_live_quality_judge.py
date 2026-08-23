from __future__ import annotations

import httpx
import pytest

from airt.quality_bridge import LiveQualityJudge, QualityJudgeResult


@pytest.mark.asyncio
async def test_live_quality_judge_parses_structured_score_without_logging_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer judge-secret"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"score": 0.86, "reason": "回答准确"}'}}]})

    client = LiveQualityJudge(base_url="http://judge.test/v1", api_key="judge-secret", model="judge-model", transport=httpx.MockTransport(handler))
    result = await client.evaluate("问题", "回答", "准确回答问题")
    assert isinstance(result, QualityJudgeResult)
    assert result.score == 0.86
    assert result.passed is True
    await client.aclose()


@pytest.mark.asyncio
async def test_live_quality_judge_rejects_malformed_response():
    client = LiveQualityJudge(base_url="http://judge.test/v1", api_key="judge-secret", model="judge-model", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})))
    with pytest.raises(RuntimeError, match="quality judge response"):
        await client.evaluate("问题", "回答", "准确")
    await client.aclose()
