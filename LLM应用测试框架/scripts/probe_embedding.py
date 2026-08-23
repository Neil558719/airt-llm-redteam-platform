"""探测 OpenAI 兼容网关：验证 key 是否有效 + 是否有 Embedding 模型。

用法（在设好环境变量的 PowerShell 里直接跑）：
    python examples/probe_embedding.py

会自动读取 LLM_BASE_URL / LLM_API_KEY（或 LLM_APP_API_KEY）/ LLM_MODEL，
也可用命令行参数覆盖：
    python examples/probe_embedding.py --base-url https://xxx/v1 --api-key sk-xxx --model gpt-4o
"""

from __future__ import annotations

import argparse
import os
import time

from openai import OpenAI

EMBED_CANDIDATES = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
    "bge-m3",
    "bge-large-zh",
    "m3e-base",
]


def main() -> None:
    ap = argparse.ArgumentParser(description="探测 OpenAI 兼容网关的 chat / embedding 可用性")
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--api-key", default=os.environ.get("LLM_API_KEY") or os.environ.get("LLM_APP_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL") or "gpt-4o-mini")
    args = ap.parse_args()

    if not args.api_key:
        print("未找到 API key：请先设置 LLM_API_KEY（或 LLM_APP_API_KEY），或用 --api-key 传入。")
        return

    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=15)
    print(f"网关: {args.base_url}")

    # 1) 聊天冒烟：先确认 key 本身有效
    try:
        r = client.chat.completions.create(
            model=args.model, messages=[{"role": "user", "content": "ping"}], max_tokens=5
        )
        print(f"  ✅ 聊天 {args.model} → key 有效，回答: {r.choices[0].message.content!r}")
    except Exception as exc:
        print(f"  ❌ 聊天 {args.model} → {type(exc).__name__}: {str(exc)[:140]}")
        print("  => key 无效 / 被网关拒绝。请先确认 key 与网关权限，再回来测 embedding。")
        return

    # 2) 探测 embedding 模型
    ok: list[str] = []
    for model in EMBED_CANDIDATES:
        t0 = time.time()
        try:
            r = client.embeddings.create(model=model, input="ping")
            print(f"  ✅ embed {model:26} dim={len(r.data[0].embedding)} ({time.time()-t0:.1f}s)")
            ok.append(model)
        except Exception as exc:
            print(f"  ❌ embed {model:26} {type(exc).__name__}: {str(exc)[:80]}")

    print("\n结论:", "有 embedding 可用：" + "、".join(ok) if ok else "网关没有可用的 embedding 模型")
    if not ok:
        print("提示: 若只是 key 权限没开 embedding，可在网关控制台给 key 加 embedding 模型权限，"
              "或换一个支持 embedding 的 key。")


if __name__ == "__main__":
    main()
