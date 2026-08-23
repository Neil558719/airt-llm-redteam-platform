from __future__ import annotations

from airt.evaluation_bridge import EvaluationContext
from airt.models import Reply, ToolCall


def test_from_reply_preserves_answer_sources_tool_calls_and_metadata():
    reply = Reply(
        text="订单已发货",
        usage={"total_tokens": 12},
        raw={"provider": "dify"},
        tool_calls=[
            ToolCall(
                id="call-1",
                name="query_order",
                arguments={"order_id": "A-1"},
                result={"status": "shipped"},
                provider="chatflow-http",
            )
        ],
    )

    context = EvaluationContext.from_reply(
        reply,
        conversation_id="conversation-1",
        latency_ms=123.4,
        sources=["订单 A-1 当前状态为已发货"],
    )

    assert context.answer == "订单已发货"
    assert context.sources == ["订单 A-1 当前状态为已发货"]
    assert context.tool_calls[0].name == "query_order"
    assert context.conversation_id == "conversation-1"
    assert context.latency_ms == 123.4
    assert context.usage == {"total_tokens": 12}


def test_to_app_response_uses_llmtest_shape_without_requiring_llmtest_import():
    context = EvaluationContext(answer="已解决", sources=["依据"])

    response = context.to_app_response()

    assert response.answer == "已解决"
    assert response.sources == ["依据"]


def test_from_reply_defaults_optional_values_to_safe_empty_values():
    context = EvaluationContext.from_reply(Reply(text="ok"))

    assert context.sources == []
    assert context.tool_calls == []
    assert context.conversation_id is None
    assert context.latency_ms is None
    assert context.raw == {}


def test_from_reply_uses_normalized_reply_sources_by_default():
    context = EvaluationContext.from_reply(Reply(text="依据回答", sources=["知识库片段"]))
    assert context.sources == ["知识库片段"]
