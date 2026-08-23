"""Machine-readable report serialization with secret-bearing fields removed."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from airt.models import CaseResult, RunMetadata, RunSummary
from airt.quality_bridge import QualitySummary

_LEGACY_METADATA = RunMetadata(
    test_type="Not recorded in original results (legacy JSONL)",
    test_method="Not recorded in original results (legacy JSONL)",
)


def _metadata(results: Sequence[CaseResult], metadata: RunMetadata | None) -> RunMetadata:
    if metadata is not None:
        return metadata
    for result in results:
        if result.run_metadata is not None:
            return result.run_metadata
    return _LEGACY_METADATA

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "credential",
    "cookie",
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _without_secrets(value: Any) -> Any:
    """Recursively remove values under keys that conventionally contain secrets."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(key) else _without_secrets(item)
            for key, item in value.items()
            if not _is_sensitive_key(key) or item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_without_secrets(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result_dump(result: CaseResult) -> dict[str, Any]:
    data = result.model_dump(mode="json")
    return _without_secrets(data)


def write_json(
    summary: RunSummary,
    results: Sequence[CaseResult],
    destination: Path,
    metadata: RunMetadata | None = None,
    quality: QualitySummary | None = None,
) -> None:
    """Write a deterministic UTF-8 JSON report without timestamps or credentials."""

    payload = {
        "metadata": _without_secrets(_metadata(results, metadata).model_dump(mode="json")),
        "summary": _without_secrets(summary.model_dump(mode="json")),
        "results": [_result_dump(result) for result in results],
    }
    if quality is not None:
        payload["quality"] = _without_secrets(quality.as_dict())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
