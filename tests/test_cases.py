import pytest

from airt.cases import CaseLoadError, load_cases


def test_load_directory_returns_unique_cases_and_excludes_sensitive(tmp_path):
    (tmp_path / "main.yaml").write_text(
        "- id: inj-001\n"
        "  name: x\n"
        "  category: prompt_injection\n"
        "  severity: high\n"
        "  turns: ['say CANARY-X']\n"
        "  detect: {canary: CANARY-X}\n",
        encoding="utf-8",
    )
    sensitive = tmp_path / "sensitive"
    sensitive.mkdir()
    (sensitive / "secret.yaml").write_text(
        "- id: sens-001\n"
        "  name: y\n"
        "  category: jailbreak\n"
        "  severity: critical\n"
        "  turns: ['private']\n"
        "  detect: {}\n",
        encoding="utf-8",
    )

    assert [case.id for case in load_cases(tmp_path)] == ["inj-001"]
    assert {case.id for case in load_cases(tmp_path, include_sensitive=True)} == {
        "inj-001",
        "sens-001",
    }


def test_loader_rejects_duplicate_ids(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "- id: x\n"
        "  name: one\n"
        "  category: jailbreak\n"
        "  severity: low\n"
        "  turns: ['hello']\n"
        "  detect: {}\n"
        "- id: x\n"
        "  name: two\n"
        "  category: jailbreak\n"
        "  severity: low\n"
        "  turns: ['hello']\n"
        "  detect: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(CaseLoadError, match="duplicate case ID"):
        load_cases(tmp_path)


def test_loader_rejects_missing_canary_in_turns(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "- id: x\n"
        "  name: one\n"
        "  category: jailbreak\n"
        "  severity: low\n"
        "  turns: ['hello']\n"
        "  detect: {canary: NOT-IN-TURNS}\n",
        encoding="utf-8",
    )

    with pytest.raises(CaseLoadError, match="canary must appear"):
        load_cases(tmp_path)
