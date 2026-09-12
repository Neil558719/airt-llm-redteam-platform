# Airt LLM 应用红队测试平台

面向 AI 应用测试与安全评估的 Python 工具链。项目以 airt CLI 为核心，对已获得授权的 LLM 应用执行安全红队测试、知识库质量回归、工具调用审计、多模态输入测试和发布前门禁，并输出可审计的 JSONL、JSON、HTML、JUnit、SARIF 与静态 Dashboard。

当前稳定版本：v0.1.0 · [GitHub Release](https://github.com/Neil558719/airt-llm-redteam-platform/releases/tag/v0.1.0)

> 仅测试你拥有或已获得明确授权的应用。项目默认使用本地无害代理工具，不执行真实订单修改、外部通知或其他现实世界副作用。

## 项目亮点

- 统一测试入口：同一套 CLI 支持 OpenAI 兼容 API、Dify Chat API 和 Dify Chatflow。
- 安全与质量双轨评测：安全用例验证注入、越权、泄露、工具滥用和资源消耗；质量用例验证知识库事实、条件完整性和回答可用性。
- 多模态输入：支持图片、音频输入测试，覆盖图片/语音伪指令、OCR 边界、敏感信息和工具误导场景。
- 真实工具观测：采集 Dify streaming 响应中的 agent_thought，审计工具名称、参数、调用次数和禁止副作用。
- 独立 Judge 与可解释结果：Judge 支持 OpenAI 兼容服务和 Anthropic；每条结果保留请求、回复、来源、工具调用、延迟、判定和失败分类。
- 工程化发布门禁：GitHub Actions + Self-hosted Runner 执行本地 Dify 实时测试；离线检查、实时安全、图片 smoke、音频 smoke、质量和 unified gate 分层运行。
- 可复现与可审计：共享 YAML 用例、统一 evaluation-result-v1 契约、运行归档、趋势、Dashboard、基线比较和 JUnit/SARIF 输出。

## 技术栈

Python 3.10+（CI 使用 Python 3.14） · Typer · Pydantic · httpx · PyYAML · Rich · Jinja2 · pytest · GitHub Actions · Dify · OpenAI-compatible API

## 能力范围

### 安全红队测试

内置用例覆盖：

- Prompt / 间接 Prompt 注入、越狱、角色扮演、目标劫持和编码混淆；
- 系统提示词、凭据、内部地址和客户信息泄露；
- 多轮会话隔离、跨用户越权、知识库权限绕过与版本污染；
- 工具参数篡改、禁止工具误调用、重复副作用、工具失败伪成功、循环调用和 SSRF；
- 输出 HTML/脚本注入、资源消耗、中英文混合攻击；
- 图片和音频中的伪指令、敏感信息、OCR/语音边界与工具误导。

安全判定遵循“攻击目标是否达成”：success 表示攻击成功，fail 表示被阻止或未达成。网络、目标服务和 Judge 错误会记录为结构化 error，不会被误判为安全通过。

### 知识库质量评测

质量链路读取统一 Chatflow 的检索来源，检查事实正确性、条件与例外是否完整、是否出现知识库无依据的承诺，并支持离线规则和实时质量 Judge。质量用例与安全用例共享同一份 YAML，避免测试问题漂移。

### 图片与音频输入

多模态用例保存在 shared_cases/multimodal_chatflow.yaml，测试资产位于 fixtures/multimodal/。单文件测试会自动匹配场景、启动临时文件服务并在测试结束后关闭：

~~~powershell
.\.venv\Scripts\airt.exe chatflow security --config config.dify.agent.yaml --asset fixtures\multimodal\prompt_injection.png --asset-type image
.\.venv\Scripts\airt.exe chatflow security --config config.dify.agent.yaml --asset fixtures\multimodal\prompt_injection.wav --asset-type audio
~~~

运行前确认 Dify Chatflow 已启用文件上传，并配置视觉模型或语音转写节点。Dify Docker 环境访问宿主机文件服务时使用 host.docker.internal。

## 快速开始

### 安装与配置

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:DIFY_AGENT_API_KEY = "<Dify API Key>"
$env:JUDGE_BASE_URL = "<Judge 网关地址>"
$env:JUDGE_API_KEY = "<Judge API Key>"
$env:JUDGE_MODEL = "<Judge 模型名>"
~~~

复制 config.example.yaml 或使用 config.dify.agent.yaml。API Key 只通过环境变量注入，不要写入 YAML 或提交到 Git。Linux/macOS 使用 .venv/bin/python 和 .venv/bin/airt。

### 运行前检查与评估

~~~powershell
.\.venv\Scripts\airt.exe doctor --config config.dify.agent.yaml --mode quality --cases shared_cases/unified_chatflow.yaml
.\.venv\Scripts\airt.exe cases validate shared_cases/unified_chatflow.yaml
.\.venv\Scripts\airt.exe chatflow security
.\.venv\Scripts\airt.exe chatflow quality
.\.venv\Scripts\airt.exe chatflow release
.\.venv\Scripts\airt.exe chatflow assess --out runs/chatflow-assess
~~~

默认 doctor 和 cases validate 不访问目标或 Judge；增加 --check-network 才进行轻量可达性探测。普通运行覆盖指定输出目录中的旧 results.jsonl；增加 --resume 才会跳过已完成用例并续跑一次。退出码 0 表示通过，1 表示门禁失败，2 表示配置或输入无效。

## 报告、趋势与基线

每次运行生成机器可读和人类可读报告，并按 UTC 时间归档：

~~~text
runs/<run>/results.jsonl
reports/security/report.json
reports/security/report.html
reports/security/archive/<UTC时间戳>/
reports/quality/
reports/assess/
~~~

~~~powershell
.\.venv\Scripts\airt.exe report --results runs/chatflow-quality/results.jsonl --out reports/quality
.\.venv\Scripts\airt.exe trend --reports reports/quality
.\.venv\Scripts\airt.exe dashboard --reports reports
.\.venv\Scripts\airt.exe baseline save --results runs/chatflow-quality/results.jsonl --out baselines/chatflow-quality.jsonl
.\.venv\Scripts\airt.exe baseline compare-assess --baseline baselines/chatflow-assess.jsonl
~~~

基线比较检查用例缺失、状态变化、回答相似度、工具调用变化和可选的延迟退化。

## CI/CD 与发布门禁

工作流位于 .github/workflows/airt-quality-security.yml，标准流程包括：

1. offline：全量 pytest、迁移静态校验、共享用例校验和离线报告；
2. shared-quality：独立质量回归；
3. live-chatflow-security：Dify Chatflow 安全用例与安全 Judge；
4. live-chatflow-image-smoke / live-chatflow-audio-smoke：独立多模态 smoke；
5. live-chatflow-quality：实时质量 Judge；
6. unified-gate：检查所有 Job、结果 artifact、统一结果契约、安全分、质量通过率和延迟预算。

实时 Job 使用标签为 self-hosted, Windows, X64, dify-local 的 Self-hosted Runner，以访问本机 Dify。所需 Secrets：

~~~text
DIFY_AGENT_API_KEY
JUDGE_BASE_URL
JUDGE_API_KEY
JUDGE_MODEL
~~~

功能分支通过 Pull Request 触发；main 的 push 会再次执行发布门禁。安全 Job 首次失败时只续跑失败用例一次，持续失败会保持红灯，不会通过降低安全标准绕过。

## 目录结构

~~~text
src/airt/                       # 核心 CLI、适配器、Runner、Judge、报告和门禁
tests/                          # 单元、集成、配置、结果契约和 CI 测试
shared_cases/                   # 共享安全/质量/多模态用例
fixtures/multimodal/            # 图片、音频测试资产
config*.yaml                    # 目标、Judge 和运行模式配置
dify_agent_tools/               # 本地无害工具和 Chatflow SQL 迁移
scripts/                        # 结果转换、比较和门禁脚本
docs/统一运行手册.md             # 完整部署、运行和排障手册
LLM应用测试框架/                  # 共享质量回归和 FastGPT 示例
.github/workflows/              # CI/CD 工作流
~~~

## 本地工具服务与 Dify 迁移

工具调用测试使用本地无害回显服务，不接触真实订单或外部地址：

~~~powershell
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "dify_agent_tools\echo_server.py 18080" -WindowStyle Hidden
Invoke-RestMethod http://127.0.0.1:18080/health
~~~

Chatflow 数据库迁移脚本位于 dify_agent_tools/。执行前请备份 Dify 数据库，并按照 docs/统一运行手册.md 操作。

## 开发与验证

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe verify_migration.py
.\.venv\Scripts\airt.exe cases validate shared_cases/unified_chatflow.yaml
git diff --check
~~~

不要提交 API Key、真实客户数据、本地 Dify 数据库文件或包含敏感内容的运行结果。更多细节见 docs/CI统一门禁说明.md、docs/架构与测试闭环.md 和 DIFY_MIGRATION_CHECKLIST.md。

## 求职项目展示要点

该项目体现的是一套接近企业日常工作的质量工程闭环：

- 将安全、质量、工具调用和多模态测试统一到可复现 CLI；
- 设计安全 Judge、失败分类、结果契约和报告归档，支持审计与趋势分析；
- 通过共享用例避免 Airt 与 pytest 两套数据漂移；
- 使用 Self-hosted Runner 把本地依赖的 Dify Chatflow 接入 PR 门禁；
- 通过独立 smoke、一次失败续跑、artifact 完整性检查和 unified gate 控制发布风险；
- 已完成从开发、验证、合并到 v0.1.0 稳定版发布的完整工程流程。

## License

当前仓库未声明开源许可证。若要公开分发，请在发布前补充明确的 License 文件和第三方依赖声明。
