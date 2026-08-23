"""Read the repository-level shared case file without depending on Airt."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
import yaml


def default_shared_case_file() -> Path:
    configured = os.environ.get("UNIFIED_CASES_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "shared_cases" / "unified_chatflow.yaml"


def load_shared_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    source = Path(path) if path else default_shared_case_file()
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"shared case file must contain a list: {source}")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict) or not item.get("case_id") or not item.get("question"):
            raise ValueError(f"invalid shared case in {source}: {item!r}")
        case_id = str(item["case_id"])
        if case_id in seen:
            raise ValueError(f"duplicate shared case_id: {case_id}")
        seen.add(case_id)
        result.append(item)
    return result


def load_quality_questions(path: str | Path | None = None) -> list[tuple[str, str, str, list[str], list[str]]]:
    """Return quality cases with required and forbidden fact keywords."""
    return [
        (
            str(item["case_id"]),
            str(item["question"]),
            str(item["expected_answer"]),
            list(item.get("quality", {}).get("required_keywords", [])),
            list(item.get("quality", {}).get("forbidden_keywords", [])),
        )
        for item in load_shared_cases(path)
        if item.get("category") in {"business", "quality"} and item.get("expected_answer")
    ]


def write_jsonl(records: list[dict[str, Any]], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")
    return destination

