"""Dify 接入探测脚本：验证 key + 打印实际响应结构。

网络受限时官方文档可能查不到，跑这个脚本看 Dify 到底返回什么，
据此微调 adapter.py 的字段解析（retriever_resources 的位置 / 字段名）。

用法（PowerShell，在项目根目录；bash 把 $env: 换成 export）：
  $env:DIFY_BASE_URL = "https://api.dify.ai/v1"   # 云版；本地部署 http://localhost/v1
  $env:DIFY_API_KEY  = "app-xxx"
  python examples/dify_bot/probe_dify.py "退货期限是几天？"
"""

import json
import os
import sys

from adapter import DifyBotApp


def _truncate(value, limit: int = 80) -> str:
    s = str(value)
    return s if len(s) <= limit else s[:limit] + "…"


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "你好"
    app = DifyBotApp()
    print(f"base_url = {app.base_url}")
    print(f"api_key  = {app.api_key[:6]}…（长度 {len(app.api_key)}）")
    if not app.api_key:
        print("警告：DIFY_API_KEY 未设置，Dify 会拒绝请求。")

    try:
        data = app._chat(
            {
                "inputs": {},
                "query": question,
                "response_mode": "blocking",
                "conversation_id": "",
                "user": "probe",
            }
        )
    except Exception as exc:
        print(f"调用失败：{exc}")
        sys.exit(1)

    print("\n响应顶层字段（值截断显示）：")
    summary = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            summary[key] = type(value).__name__
        else:
            summary[key] = _truncate(value)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("\nanswer 前 200 字：", _truncate(data.get("answer", ""), 200))
    print("\n检索来源 sources：")
    sources = app._extract_sources(data)
    if sources:
        for i, s in enumerate(sources, 1):
            print(f"  [{i}] {_truncate(s, 100)}")
    else:
        print("  （空 —— 应用可能未启用知识库检索，幻觉检测无从核对）")


if __name__ == "__main__":
    main()
