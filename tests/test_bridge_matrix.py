from __future__ import annotations

import pytest

from airt.evaluation_bridge import EvaluationContext
from airt.models import Reply, ToolCall


@pytest.mark.parametrize(
    ("target_name", "reply"),
    [
        ("airt_dify_text", Reply(text="Airt 文本", raw={"provider": "dify"})),
        (
            "airt_dify_chatflow",
            Reply(
                text="Airt Chatflow",
                raw={"provider": "dify", "mode": "streaming"},
                tool_calls=[ToolCall(name="query_order", provider="chatflow-http")],
            ),
        ),
    ],
)
def test_all_registered_application_families_share_one_evaluation_shape(target_name, reply):
    context = EvaluationContext.from_reply(
        reply,
        conversation_id=f"{target_name}-conversation",
        latency_ms=10.0,
        sources=[f"{target_name} source"],
    )

    assert context.answer
    assert context.sources == [f"{target_name} source"]
    assert context.conversation_id.endswith("-conversation")
    assert context.to_app_response().answer == context.answer
