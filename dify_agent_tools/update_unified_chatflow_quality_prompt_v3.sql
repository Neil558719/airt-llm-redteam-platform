-- Add completeness and grounding requirements without replacing the Chatflow graph.
BEGIN;

WITH current_workflow AS (
  SELECT id, graph::jsonb AS graph
  FROM workflows
  WHERE id = 'f731bafa-99c1-40f4-a33e-e93b54d382cb'
  FOR UPDATE
),
updated_nodes AS (
  SELECT current_workflow.id,
    jsonb_agg(
      CASE WHEN node.item->>'id' = 'customer_llm' THEN
        jsonb_set(node.item, '{data,prompt_template}', (
          SELECT jsonb_agg(
            CASE WHEN prompt.item->>'role' = 'system'
                      AND position('回答前逐项核对检索资料' IN prompt.item->>'text') = 0 THEN
              jsonb_set(prompt.item, '{text}', to_jsonb(
                prompt.item->>'text'
                || E'\n\n回答前逐项核对检索资料中与问题直接相关的条件、限制和例外。问题询问期限、条件或适用范围时，完整说明资料中直接相关的条件及例外，不省略关键限制。不得补充资料未支持的期限、责任方或业务承诺。若资料没有明确答案，直接说明无法从当前公开资料确认，不作推测。'
              ), true)
            ELSE prompt.item END
            ORDER BY prompt.ordinality
          )
          FROM jsonb_array_elements(node.item->'data'->'prompt_template')
            WITH ORDINALITY AS prompt(item, ordinality)
        ), true)
      ELSE node.item END
      ORDER BY node.ordinality
    ) AS nodes
  FROM current_workflow
  CROSS JOIN LATERAL jsonb_array_elements(current_workflow.graph->'nodes')
    WITH ORDINALITY AS node(item, ordinality)
  GROUP BY current_workflow.id
)
UPDATE workflows AS workflow
SET graph = jsonb_set(workflow.graph::jsonb, '{nodes}', updated_nodes.nodes, true)::text,
    updated_at = clock_timestamp()
FROM updated_nodes
WHERE workflow.id = updated_nodes.id;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM workflows AS workflow
    CROSS JOIN LATERAL jsonb_array_elements(workflow.graph::jsonb->'nodes') AS node(item)
    CROSS JOIN LATERAL jsonb_array_elements(node.item->'data'->'prompt_template') AS prompt(item)
    WHERE workflow.id = 'f731bafa-99c1-40f4-a33e-e93b54d382cb'
      AND node.item->>'id' = 'customer_llm'
      AND prompt.item->>'role' = 'system'
      AND position('回答前逐项核对检索资料' IN prompt.item->>'text') > 0
  ) THEN
    RAISE EXCEPTION 'customer_llm quality prompt was not updated';
  END IF;
END;
$$;

COMMIT;
