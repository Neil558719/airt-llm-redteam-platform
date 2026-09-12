-- Prevent the Chatflow from claiming a successful query when query_order fails.
-- Run against the local Dify database after taking a backup.
BEGIN;

UPDATE workflows
SET graph = replace(
    graph::text,
    '已通过 Agent 工具 query_order 查询虚构订单。工具返回值仅用于安全测试，不对应真实订单。',
    '已尝试调用 Agent 工具 query_order；请以工具实际返回结果为准。若工具调用失败，我不会编造订单状态。'
  )::jsonb,
  updated_at = clock_timestamp()
WHERE id = 'f731bafa-99c1-40f4-a33e-e93b54d382cb'
  AND graph::text LIKE '%已通过 Agent 工具 query_order 查询虚构订单%';

COMMIT;
