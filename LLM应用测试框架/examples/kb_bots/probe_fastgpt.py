"""FastGPT 接入探针：验证 key + appId + 打印回答与检索来源。

跑这个脚本看 FastGPT 是否配置正确。走 adapter 的 ask()（含 appId 逻辑），
避免手拼 payload 漏掉关键字段。

用法（PowerShell，在项目根目录）：
  $env:FASTGPT_BASE_URL = "http://127.0.0.1:3000"
  $env:FASTGPT_API_KEY  = "fastgpt-xxx"
  $env:FASTGPT_APP_ID   = "24位AgentID"
  python examples/kb_bots/probe_fastgpt.py "退货期限是几天？"
"""

import sys

from adapter_fastgpt import FastGPTApp


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "你好"
    app = FastGPTApp()
    print(f"base_url = {app.base_url}")
    print(f"api_key  = {app.api_key[:6]}…（长度 {len(app.api_key)}）")
    print(f"app_id   = {app.app_id or '（未设置！请设 FASTGPT_APP_ID）'}")
    if not app.api_key:
        print("警告：FASTGPT_API_KEY 未设置，FastGPT 会拒绝请求。")

    try:
        resp = app.ask(question)
    except Exception as exc:
        print(f"调用失败：{exc}")
        sys.exit(1)

    print(f"\nanswer 前 200 字：{resp.answer[:200]}")
    print("\n检索来源 sources：")
    if resp.sources:
        for i, s in enumerate(resp.sources, 1):
            print(f"  [{i}] {s[:100]}")
    else:
        print("  （空 —— FastGPT 兼容接口未返回引用，幻觉检测用例会跳过）")
    print(f"chatId/conversation：{app.last_conversation_id or '（无）'}")


if __name__ == "__main__":
    main()
