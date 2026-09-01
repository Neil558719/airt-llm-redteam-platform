import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _graph_from_update_sql(path: Path) -> dict:
    sql = path.read_text(encoding="utf-8")
    match = re.search(r'''SET graph = '(?P<graph>\{"nodes".*?\})', features''', sql, re.DOTALL)
    assert match, f"could not find graph JSON in {path}"
    return json.loads(match.group("graph").replace("''", "'"))


@pytest.mark.parametrize(
    ("filename", "node_id"),
    [
        ("update_unified_chatflow_knowledge_llm.sql", "customer-llm"),
        ("update_unified_chatflow_knowledge_llm_v2.sql", "customer_llm"),
    ],
)
def test_chatflow_customer_llm_receives_images_and_has_vision_enabled(filename: str, node_id: str):
    sql_path = ROOT / "dify_agent_tools" / filename
    graph = _graph_from_update_sql(sql_path)
    llm = next(node for node in graph["nodes"] if node["id"] == node_id)

    assert llm["data"]["vision"]["enabled"] is True
    user_prompt_item = next(item for item in llm["data"]["prompt_template"] if item["role"] == "user")
    user_prompt = user_prompt_item["text"]
    assert "{{#sys.files#}}" in user_prompt
    assert llm["data"]["vision"]["configs"]["variable_selector"] == ["sys", "files"]
    assert llm["data"]["model"]["provider"] == "langgenius/tongyi/tongyi"
    assert llm["data"]["model"]["name"] == "qwen-vl-max"
    assert '"file_upload":{"enabled":true}' in sql_path.read_text(encoding="utf-8")


def test_in_place_multimodal_migration_preserves_existing_workflow_nodes():
    sql = (ROOT / "dify_agent_tools" / "enable_chatflow_multimodal_files.sql").read_text(encoding="utf-8")

    assert "jsonb_array_elements" in sql
    assert "jsonb_build_object" in sql
    assert "multimodal_normalizer" in sql
    assert "customer_llm" in sql
    assert "jsonb_build_array('sys', 'files')" in sql
    assert "qwen-vl-max" in sql
