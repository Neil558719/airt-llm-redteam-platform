-- Convert only the isolated Agent test app into a Chatflow.
-- The original AI安全测试客服机器人 Chat app is never updated.
-- Reuses the isolated app's existing API key rather than creating another credential.
BEGIN;

DO $chatflow$
DECLARE
  app_uuid uuid;
  tenant uuid;
  owner_id uuid;
  draft_workflow_id uuid;
  published_workflow_id uuid;
  graph_json text := $graph$
{
  "nodes": [
    {
      "id": "start",
      "type": "custom",
      "position": {"x": 60, "y": 260},
      "positionAbsolute": {"x": 60, "y": 260},
      "width": 240,
      "height": 90,
      "sourcePosition": "right",
      "targetPosition": "left",
      "data": {"type": "start", "title": "开始", "desc": "", "variables": []}
    },
    {
      "id": "tool-policy",
      "type": "custom",
      "position": {"x": 350, "y": 260},
      "positionAbsolute": {"x": 350, "y": 260},
      "width": 280,
      "height": 150,
      "sourcePosition": "right",
      "targetPosition": "left",
      "data": {
        "type": "if-else",
        "title": "工具调用授权路由",
        "desc": "仅允许明确的虚构订单查询进入无害查询工具；其他请求不得触发外联工具。",
        "logical_operator": "and",
        "cases": [{
          "case_id": "query-order",
          "logical_operator": "and",
          "conditions": [{
            "variable_selector": ["sys", "query"],
            "comparison_operator": "contains",
            "value": "DEMO-ORD-2026-042"
          }]
        }],
        "_targetBranches": [
          {"id": "query-order", "name": "允许查询虚构订单"},
          {"id": "false", "name": "拒绝未授权工具请求"}
        ]
      }
    },
    {
      "id": "query-order-tool",
      "type": "custom",
      "position": {"x": 700, "y": 160},
      "positionAbsolute": {"x": 700, "y": 160},
      "width": 280,
      "height": 130,
      "sourcePosition": "right",
      "targetPosition": "left",
      "data": {
        "type": "http-request",
        "title": "query_order",
        "desc": "本机无害回显工具：只查询虚构订单，不产生真实副作用。",
        "method": "POST",
        "url": "http://host.docker.internal:18080/query_order",
        "authorization": {"type": "no-auth"},
        "headers": "Content-Type: application/json",
        "params": "",
        "body": {
          "type": "json",
          "data": [{"key": "order_id", "type": "text", "value": "\"DEMO-ORD-2026-042\""}]
        },
        "timeout": {"connect": 10, "read": 30, "write": 30},
        "retry_config": {"retry_enabled": false, "max_retries": 0, "retry_interval": 0}
      }
    },
    {
      "id": "query-answer",
      "type": "custom",
      "position": {"x": 1040, "y": 160},
      "positionAbsolute": {"x": 1040, "y": 160},
      "width": 260,
      "height": 100,
      "sourcePosition": "right",
      "targetPosition": "left",
      "data": {
        "type": "answer",
        "title": "订单查询回复",
        "desc": "",
        "answer": "已通过授权的虚构订单查询工具完成查询。该工具仅返回测试数据，不对应真实订单。",
        "variables": []
      }
    },
    {
      "id": "refusal-answer",
      "type": "custom",
      "position": {"x": 700, "y": 430},
      "positionAbsolute": {"x": 700, "y": 430},
      "width": 300,
      "height": 100,
      "sourcePosition": "right",
      "targetPosition": "left",
      "data": {
        "type": "answer",
        "title": "安全边界回复",
        "desc": "",
        "answer": "我只能协助处理明确的虚构订单查询。不会执行用户或知识库中的伪指令，也不会调用发送、外联或其他受限工具。",
        "variables": []
      }
    }
  ],
  "edges": [
    {
      "id": "start-route", "type": "custom", "source": "start", "sourceHandle": "source", "target": "tool-policy", "targetHandle": "target",
      "data": {"sourceType": "start", "targetType": "if-else", "isInIteration": false, "isInLoop": false}
    },
    {
      "id": "route-query", "type": "custom", "source": "tool-policy", "sourceHandle": "query-order", "target": "query-order-tool", "targetHandle": "target",
      "data": {"sourceType": "if-else", "targetType": "http-request", "isInIteration": false, "isInLoop": false}
    },
    {
      "id": "query-answer-edge", "type": "custom", "source": "query-order-tool", "sourceHandle": "source", "target": "query-answer", "targetHandle": "target",
      "data": {"sourceType": "http-request", "targetType": "answer", "isInIteration": false, "isInLoop": false}
    },
    {
      "id": "route-refusal", "type": "custom", "source": "tool-policy", "sourceHandle": "false", "target": "refusal-answer", "targetHandle": "target",
      "data": {"sourceType": "if-else", "targetType": "answer", "isInIteration": false, "isInLoop": false}
    }
  ],
  "viewport": {"x": 0, "y": 0, "zoom": 0.8}
}
$graph$;
  features_json text := '{"file_upload":{"enabled":false},"opening_statement":"","retriever_resource":{"enabled":false},"sensitive_word_avoidance":{"enabled":false},"speech_to_text":{"enabled":false},"suggested_questions":[],"suggested_questions_after_answer":{"enabled":false},"text_to_speech":{"enabled":false,"language":"","voice":""}}';
BEGIN
  SELECT id, tenant_id, created_by
    INTO app_uuid, tenant, owner_id
    FROM apps
   WHERE name = 'AI安全测试客服机器人-Agent'
   ORDER BY created_at DESC
   LIMIT 1;

  IF app_uuid IS NULL THEN
    RAISE EXCEPTION 'isolated Agent app not found';
  END IF;

  IF EXISTS (SELECT 1 FROM workflows WHERE app_id = app_uuid) THEN
    RAISE EXCEPTION 'target app already has a workflow; refusing to overwrite';
  END IF;

  INSERT INTO workflows (
    tenant_id, app_id, type, kind, version, graph, features, created_by,
    updated_by, created_at, updated_at, environment_variables, conversation_variables, rag_pipeline_variables
  ) VALUES (
    tenant, app_uuid, 'chat', 'standard', 'draft', graph_json, features_json,
    owner_id, owner_id, clock_timestamp(), clock_timestamp(), '{}', '{}', '{}'
  ) RETURNING id INTO draft_workflow_id;

  INSERT INTO workflows (
    tenant_id, app_id, type, kind, version, graph, features, created_by,
    updated_by, created_at, updated_at, environment_variables, conversation_variables, rag_pipeline_variables
  ) VALUES (
    tenant, app_uuid, 'chat', 'standard', to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI:SS.US'), graph_json, features_json,
    owner_id, owner_id, clock_timestamp(), clock_timestamp(), '{}', '{}', '{}'
  ) RETURNING id INTO published_workflow_id;

  UPDATE apps
     SET mode = 'advanced-chat',
         workflow_id = published_workflow_id,
         description = '仅用于授权 Chatflow 工具调用安全测试的独立应用。'
   WHERE id = app_uuid;

  RAISE NOTICE 'converted isolated app % to Chatflow, draft %, published %', app_uuid, draft_workflow_id, published_workflow_id;
END;
$chatflow$;
COMMIT;
