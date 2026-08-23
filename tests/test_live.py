"""Opt-in smoke test for an explicitly configured OpenAI-compatible target."""

import os

import pytest

from airt.adapter import OpenAICompatTarget
from airt.config import TargetConfig
from airt.models import Message


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openai_compatible_target() -> None:
    required = ["AIRT_LIVE_BASE_URL", "AIRT_LIVE_API_KEY", "AIRT_LIVE_MODEL"]
    if not all(os.getenv(name) for name in required):
        pytest.skip("set AIRT_LIVE_BASE_URL, AIRT_LIVE_API_KEY and AIRT_LIVE_MODEL")

    target = OpenAICompatTarget(
        TargetConfig(
            base_url=os.environ[required[0]],
            api_key=os.environ[required[1]],
            model=os.environ[required[2]],
            timeout=30,
        )
    )
    try:
        reply = await target.chat(
            [Message(role="user", content="Reply with the word READY only.")]
        )
        assert reply.text
    finally:
        await target.aclose()
