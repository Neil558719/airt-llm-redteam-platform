"""Validation for the safe, Dify-specific knowledge-base case library."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from airt.cases import load_cases


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "cases" / "dify.yaml"
KNOWLEDGE_PATH = ROOT / "knowledge" / "dify"
EXPECTED = {
    "dify-kb-001": ("indirect_injection", "high"),
    "dify-kb-002": ("indirect_injection", "high"),
    "dify-system-001": ("data_exfiltration", "high"),
    "dify-roleplay-001": ("roleplay", "medium"),
    "dify-goal-001": ("goal_hijacking", "medium"),
}
KEY_LIKE_LITERAL = re.compile(
    r"(?i)\b(?:sk|api|app)[_-][a-z0-9]{8,}\b|\b(?:bearer|authorization)\s+[a-z0-9._-]{8,}"
)


def test_dify_case_library_loads_with_expected_ids_categories_and_severities():
    cases = load_cases(CASES_PATH)

    assert {case.id: (case.category.value, case.severity.value) for case in cases} == EXPECTED


def test_dify_case_yaml_uses_attack_oriented_judge_goals_and_chinese_names():
    document = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))

    assert isinstance(document, list)
    by_id = {item["id"]: item for item in document}
    assert by_id["dify-kb-001"]["name"] == "知识库测试夹具伪指令标记"
    assert by_id["dify-kb-002"]["name"] == "知识库伪指令边界"
    assert by_id["dify-system-001"]["name"] == "系统提示词披露边界"
    assert by_id["dify-roleplay-001"]["name"] == "虚构经理角色边界"
    assert by_id["dify-goal-001"]["name"] == "订单客服目标劫持边界"
    assert by_id["dify-kb-001"]["detect"] == {
        "canary": "DIFY-KB-CANARY-001",
        "judge": "never",
    }

    for case_id in set(EXPECTED) - {"dify-kb-001"}:
        detect = by_id[case_id]["detect"]
        assert detect["judge"] == "auto"
        assert detect["judge_goal"].startswith("攻击者试图")
        assert "仅当回复实际" in detect["judge_goal"]
        assert not any(
            marker in detect["judge_goal"]
            for marker in ("回复是否拒绝", "回复是否保持", "回复是否避免", "回复是否没有")
        )


def test_dify_canaries_are_present_in_a_turn_when_configured():
    for case in load_cases(CASES_PATH):
        if case.detect.canary:
            assert any(case.detect.canary in turn for turn in case.turns)


def test_dify_knowledge_and_cases_contain_no_key_like_literals():
    sources = [CASES_PATH, *sorted(KNOWLEDGE_PATH.glob("*.md"))]

    assert len(sources) == 4
    for source in sources:
        assert not KEY_LIKE_LITERAL.search(source.read_text(encoding="utf-8")), source
