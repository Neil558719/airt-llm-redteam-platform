from __future__ import annotations

import json
import re
from pathlib import Path

from graphon.nodes.answer.entities import AnswerNodeData
from graphon.nodes.http_request.entities import HttpRequestNodeData
from graphon.nodes.if_else.entities import IfElseNodeData

sql = Path("/tmp/migrate_agent_to_chatflow.sql").read_text(encoding="utf-8")
match = re.search(r"graph_json text := \$graph\$(.*?)\$graph\$;", sql, re.DOTALL)
if match is None:
    raise RuntimeError("could not locate graph JSON in provisioning SQL")
graph = json.loads(match.group(1))

for node in graph["nodes"]:
    data = node["data"]
    if data["type"] == "if-else":
        IfElseNodeData.model_validate(data)
    elif data["type"] == "http-request":
        HttpRequestNodeData.model_validate(data)
    elif data["type"] == "answer":
        AnswerNodeData.model_validate(data)

print("Dify node validation passed")
