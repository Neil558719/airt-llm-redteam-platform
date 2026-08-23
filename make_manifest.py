from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "MIGRATION-MANIFEST.json"
EXCLUDE = {"MIGRATION-MANIFEST.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


files = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path.name in EXCLUDE:
        continue
    files.append(
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
    )

manifest = {
    "format": 1,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "source": "current working tree snapshot; credentials and runtime artifacts excluded",
    "generator_python": sys.version,
    "generator_platform": platform.platform(),
    "files": files,
}
OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(files)} files)")
