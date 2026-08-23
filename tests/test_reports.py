"""Tests for deterministic report renderers."""

from __future__ import annotations

import json

from airt.report.console import render_console
from airt.report.html import render_html
from airt.report.json_report import write_json


def test_json_report_contains_exclusions_and_case_details(summary_and_results, tmp_path):
    destination = tmp_path / "report.json"
    write_json(*summary_and_results, destination)
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert data["summary"]["asr"] == summary_and_results[0].asr
    assert {item["case_id"] for item in data["results"]} == {
        "pass",
        "fail",
        "uncertain",
        "error",
    }
    assert data["results"][0]["messages"]
    assert data["results"][0]["reply"]["text"] == "CANARY-PASS"
    assert data["results"][0]["verdict"]["source"] == "rule"


def test_html_report_is_self_contained_and_uses_chinese_readable_content(
    summary_and_results, tmp_path
):
    destination = tmp_path / "report.html"
    render_html(*summary_and_results, destination)
    html = destination.read_text(encoding="utf-8")
    assert '<html lang="zh-CN">' in html
    assert "<style>" in html and "<script>" in html
    assert "https://" not in html
    assert "攻击成功率（ASR）" in html
    assert "AI 红队测试报告" in html
    assert "测试请求" in html and "模型回复" in html and "判定结论" in html
    assert "按严重级别筛选" in html
    assert "CANARY-PASS" in html
    assert "canary matched" in html
    assert "TimeoutError: target unavailable" in html
    assert '"role":' not in html
    assert '"content":' not in html
    assert '"verdict":' not in html
    assert "prefers-color-scheme" in html
    assert "severity-filter" in html
    assert "<details" in html


def test_html_report_shows_only_final_reply_not_adapter_raw(summary_and_results, tmp_path):
    summary, results = summary_and_results
    results[0].reply.raw = {
        "conversation_id": "private-conversation-id",
        "usage": {"api_key": "secret-value"},
    }
    destination = tmp_path / "report.html"
    render_html(summary, results, destination)
    html = destination.read_text(encoding="utf-8")
    assert "CANARY-PASS" in html
    assert "private-conversation-id" not in html
    assert "secret-value" not in html
    assert "conversation_id" not in html


def test_html_report_escapes_model_output(summary_and_results, tmp_path):
    summary, results = summary_and_results
    results[0].reply.text = '<script>alert("x")</script>'
    destination = tmp_path / "report.html"
    render_html(summary, results, destination)
    html = destination.read_text(encoding="utf-8")
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;alert" in html


def test_console_report_is_chinese_and_shows_every_case(summary_and_results, capsys):
    render_console(*summary_and_results)
    output = capsys.readouterr().out
    assert "AI 红队测试报告" in output
    assert "攻击成功率（ASR）" in output and "1/2" in output
    assert "结论不确定" in output and "执行异常" in output
    assert "提示注入" in output
    for case_id in ("pass", "fail", "uncertain", "error"):
        assert case_id in output
    assert "测试请求" in output and "模型回复" in output and "判定结论" in output
    assert "CANARY-PASS" in output
    assert "TimeoutError: target unavailable" in output
    assert "maximum five" not in output
