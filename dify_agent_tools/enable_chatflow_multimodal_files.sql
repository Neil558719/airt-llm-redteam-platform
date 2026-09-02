-- Preserve the existing Chatflow graph and bind uploaded files to its LLM nodes.
-- Run against the isolated test Chatflow workflow, then publish the workflow again.
BEGIN;

WITH updated_graph AS (
  SELECT
    w.id,
    jsonb_set(
      w.graph::jsonb,
      '{nodes}',
      (
        SELECT jsonb_agg(
          CASE
            WHEN node.item->>'id' IN ('multimodal_normalizer', 'customer_llm') THEN
              jsonb_set(
                jsonb_set(
                  node.item,
                  '{data,vision}',
                  COALESCE(node.item->'data'->'vision', '{}'::jsonb) || jsonb_build_object(
                    'enabled', true,
                    'configs', jsonb_build_object(
                      'detail', 'high',
                      'variable_selector', jsonb_build_array('sys', 'files')
                    )
                  ),
                  true
                ),
                '{data,prompt_template}',
                (
                  SELECT jsonb_agg(
                    CASE
                      WHEN prompt.item->>'role' = 'user' THEN
                        jsonb_set(
                          prompt.item,
                          '{text}',
                          to_jsonb(
                            COALESCE(prompt.item->>'text', '')
                            || E'\\n\\n附件：{{#sys.files#}}'
                          ),
                          true
                        )
                      ELSE prompt.item
                    END
                    ORDER BY prompt.ordinality
                  )
                  FROM jsonb_array_elements(node.item->'data'->'prompt_template')
                    WITH ORDINALITY AS prompt(item, ordinality)
                ),
                true
              )
            ELSE node.item
          END
          ORDER BY node.ordinality
        )
        FROM jsonb_array_elements(w.graph::jsonb->'nodes')
          WITH ORDINALITY AS node(item, ordinality)
      ),
      true
    ) AS graph
  FROM workflows AS w
  WHERE w.id = 'f731bafa-99c1-40f4-a33e-e93b54d382cb'
)
UPDATE workflows AS w
SET graph = updated_graph.graph::text,
    features = jsonb_set(
      COALESCE(w.features::jsonb, '{}'::jsonb),
      '{file_upload,enabled}',
      'true'::jsonb,
      true
    )::text,
    updated_at = clock_timestamp()
FROM updated_graph
WHERE w.id = updated_graph.id;

UPDATE workflows
SET graph = jsonb_set(
  graph::jsonb,
  '{nodes}',
  (
    SELECT jsonb_agg(
      CASE WHEN node.item->>'id' = 'customer_llm' THEN
        jsonb_set(
          jsonb_set(node.item, '{data,model,provider}', to_jsonb('langgenius/tongyi/tongyi'::text), true),
          '{data,model,name}', to_jsonb('qwen-vl-max'::text), true
        )
      ELSE node.item END
      ORDER BY node.ordinality
    )
    FROM jsonb_array_elements(graph::jsonb->'nodes') WITH ORDINALITY AS node(item, ordinality)
  ),
  true
)::text,
updated_at = clock_timestamp()
WHERE id = 'f731bafa-99c1-40f4-a33e-e93b54d382cb';

COMMIT;
