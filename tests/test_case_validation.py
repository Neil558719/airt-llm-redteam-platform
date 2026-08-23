from pathlib import Path

from airt.case_validation import validate_cases


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_validate_shared_chatflow_cases():
    summary = validate_cases("shared_cases/unified_chatflow.yaml")
    assert summary.valid
    assert summary.cases == 8


def test_validate_rejects_duplicate_ids(tmp_path):
    write(tmp_path / "a.yaml", "- id: same\n  name: A\n  category: jailbreak\n  severity: low\n  turns: ['x']\n")
    write(tmp_path / "b.yaml", "- id: same\n  name: B\n  category: jailbreak\n  severity: low\n  turns: ['y']\n")
    summary = validate_cases(tmp_path)
    assert not summary.valid
    assert any("重复用例 ID" in issue.message for issue in summary.issues)


def test_validate_reports_invalid_document(tmp_path):
    write(tmp_path / "bad.yaml", "{}\n")
    summary = validate_cases(tmp_path / "bad.yaml")
    assert not summary.valid
    assert summary.issues

