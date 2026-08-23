"""JSON 与 JSON Schema 校验断言。"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..metrics.tracker import tracker


def assert_valid_json(text: str) -> Any:
    """断言文本是合法 JSON，返回解析结果。失败抛 AssertionError。

    真实模型可能把 JSON 包在 ```json 代码块里，先严格解析，失败再用稳健提取兜底。
    """
    text = (text or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            from ..clients.base import extract_json

            data = extract_json(text)
        except ValueError as exc:
            message = f"JSON 解析失败: {exc}\n原文: {text[:400]}"
            tracker.add_assertion("assert_valid_json", False, message)
            raise AssertionError(message) from exc
    tracker.add_assertion("assert_valid_json", True, "JSON 解析成功")
    return data


def assert_json_schema(data: Any, schema: Dict[str, Any]) -> None:
    """断言数据符合 JSON Schema。列出所有校验错误。"""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("assert_json_schema 需要 jsonschema 库：pip install jsonschema") from exc

    validator = jsonschema.Draft7Validator(schema)
    errors: List[jsonschema.ValidationError] = sorted(validator.iter_errors(data), key=str)
    if not errors:
        tracker.add_assertion("assert_json_schema", True, "JSON Schema 校验通过")
        return

    lines = []
    for err in errors[:20]:
        path = "/".join(str(p) for p in err.absolute_path) or "$"
        lines.append(f"  - {path}: {err.message}")
    if len(errors) > 20:
        lines.append(f"  … 共 {len(errors)} 处错误，仅显示前 20 处")
    message = f"JSON Schema 校验失败（{len(errors)} 处）:\n" + "\n".join(lines)
    tracker.add_assertion("assert_json_schema", False, message)
    raise AssertionError(message)
