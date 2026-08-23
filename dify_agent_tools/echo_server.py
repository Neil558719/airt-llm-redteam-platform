#!/usr/bin/env python3
"""无害安全测试回显服务（仅用于授权测试）。

用途：作为 Dify 自定义 HTTP 工具的调用目标。
- 记录每一次入站请求（方法/路径/头/正文）到控制台；
- 始终返回固定 canary JSON，绝不含任何真实数据、密钥或敏感信息。

只应在你拥有或已获明确授权的测试环境中运行。
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 无害标记：仅用于在测试结果里确认"工具是否真的被调用"。
CANARY = "TOOL-ECHO-CANARY-9F2A"


class EchoHandler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        record = {
            "method": self.command,
            "path": parsed.path,
            "query": query,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body,
        }
        # 打印到控制台，方便在 Dify 预览/airt 运行期间实时确认调用是否发生。
        print(f"[echo] {json.dumps(record, ensure_ascii=False)}", flush=True)

        payload = json.dumps(
            {"ok": True, "canary": CANARY, "echo": body or query}, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, *args) -> None:  # 关闭默认访问日志噪音
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    server = ThreadingHTTPServer(("0.0.0.0", port), EchoHandler)
    print(
        f"[echo] listening on http://0.0.0.0:{port}  canary={CANARY}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[echo] stopped", flush=True)


if __name__ == "__main__":
    main()
