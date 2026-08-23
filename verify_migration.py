from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "pyproject.toml",
    "README.md",
    "src/airt/cli.py",
    "src/airt/config.py",
    "src/airt/dify_adapter.py",
    "src/airt/models.py",
    "cases/dify.yaml",
    "cases/dify-agent.yaml",
    "config.dify.yaml",
    "config.dify.agent.yaml",
    "dify_agent_tools/custom_tool_openapi.yaml",
    "dify_agent_tools/echo_server.py",
)
FORBIDDEN_NAMES = {".env", ".git", ".claude", ".venv", "__pycache__", ".pytest_cache", "runs", "reports"}
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])app-[A-Za-z0-9_-]{20,}"),
)


def iter_project_files(root: Path):
    """Yield migration files while excluding generated/runtime directories."""
    for path in root.rglob("*"):
        if any(part in FORBIDDEN_NAMES for part in path.relative_to(root).parts):
            continue
        yield path


def main() -> int:
    problems: list[str] = []
    if sys.version_info < (3, 10):
        problems.append(f"Python >=3.10 required, found {sys.version.split()[0]}")
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            problems.append(f"missing required file: {relative}")
    for path in iter_project_files(ROOT):
        if path.is_file() and path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as error:
                problems.append(f"Python syntax error in {path.relative_to(ROOT)}: {error}")
        if path.is_file() and path.suffix in {".yaml", ".yml", ".md", ".txt", ".toml", ".ps1"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    problems.append(f"review possible secret in {path.relative_to(ROOT)}")
    if os.environ.get("DIFY_AGENT_API_KEY"):
        print("WARNING: DIFY_AGENT_API_KEY is set in this shell; clear it for isolated tests.")
    if problems:
        print("Migration verification failed:")
        print("\n".join(f"- {problem}" for problem in problems))
        return 1
    print(f"Migration verification passed for Python {sys.version.split()[0]}")
    print("Next: install with pip install -e ., then run airt --help and offline tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
