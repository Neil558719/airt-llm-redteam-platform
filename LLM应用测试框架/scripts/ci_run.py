"""CI 运行脚本：两档测试一条命令（Mock 冒烟 + 真实回归），报告作为 CI 产物。

用法（项目根目录）：
  # 只 Mock 冒烟（无需 key，秒级，CI 快速检查）
  python scripts/ci_run.py --smoke

  # 真实回归（需配好平台 + 裁判 key）
  python scripts/ci_run.py --regression --app fastgpt \
    --llm-mode real --llm-provider openai --llm-base-url https://newapi.gosuncn.com/v1 \
    --llm-model gpt-5.6-sol --llm-api-key sk-裁判key

  # 全量（先冒烟后回归）
  python scripts/ci_run.py --all --app dify --llm-* ...

真实回归默认启用：用例级超时（--timeout）+ 偶发失败重试（--reruns），
需要安装 ci extras：pip install -e ".[ci]"
"""

import argparse
import subprocess
import sys


def _run(cmd: list) -> int:
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description="llmtest CI 运行")
    ap.add_argument("--smoke", action="store_true", help="Mock 冒烟（tests/，无需 key）")
    ap.add_argument("--regression", action="store_true", help="真实回归（examples/kb_bots/）")
    ap.add_argument("--all", action="store_true", help="先冒烟后回归")
    ap.add_argument("--app", default="fastgpt", help="被测平台：dify | fastgpt")
    ap.add_argument("--llm-mode", default="real")
    ap.add_argument("--llm-provider", default="openai")
    ap.add_argument("--llm-model", default="gpt-5.6-sol")
    ap.add_argument("--llm-base-url", default=None)
    ap.add_argument("--llm-api-key", default="")
    # 超时 / 重试（依赖 ci extras）
    ap.add_argument("--timeout", type=int, default=900, help="单用例超时秒数（默认 900）")
    ap.add_argument("--reruns", type=int, default=1, help="偶发失败重试次数（默认 1）")
    args = ap.parse_args()

    if not (args.smoke or args.regression or args.all):
        ap.error("至少指定 --smoke / --regression / --all")

    smoke_cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]

    # 真实回归：数据驱动问题集 + 超时 + 重试 + 报告
    regress_cmd = [
        sys.executable, "-m", "pytest", "examples/kb_bots/",
        "--app", args.app,
        "--llm-mode", args.llm_mode,
        "--llm-provider", args.llm_provider,
        "--llm-model", args.llm_model,
        "--timeout", str(args.timeout),
        "--reruns", str(args.reruns),
        "--reruns-delay", "5",
    ]
    if args.llm_base_url:
        regress_cmd += ["--llm-base-url", args.llm_base_url]
    if args.llm_api_key:
        regress_cmd += ["--llm-api-key", args.llm_api_key]

    rc = 0
    if args.all or args.smoke:
        rc = _run(smoke_cmd) or rc
    if args.all or args.regression:
        rc = _run(regress_cmd) or rc

    status = "全部通过" if rc == 0 else "存在失败"
    print(f"\n===== CI 结果：{status}（退出码 {rc}）=====")
    print("报告：reports/llm_test_report.html（真实回归生成）")
    sys.exit(rc)


if __name__ == "__main__":
    main()
