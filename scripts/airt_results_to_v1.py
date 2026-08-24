"""Convert Airt CaseResult JSONL into the shared evaluation-result-v1 contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from airt.models import CaseResult
from airt.unified_results import from_airt


def convert(source: Path, destination: Path) -> int:
    records: list[str] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            result = CaseResult.model_validate_json(line)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid Airt JSONL at {source}:{line_number}") from error
        records.append(json.dumps(from_airt(result), ensure_ascii=False))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(records) + ("\n" if records else ""), encoding="utf-8")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    count = convert(args.input, args.output)
    print(f"converted {count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
