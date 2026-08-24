# AI 红队测试工具

`airt` 是一个面向 LLM 应用的命令行安全测试工具。它可以通过 OpenAI 兼容 HTTP API 或原生 Dify Chat API 对你拥有或已获得明确授权的应用执行红队测试。

## 安装

需要 Python 3.10 或更高版本。使用以下命令以可编辑模式安装项目及测试依赖：

```bash
python -m pip install -e ".[test]"
```

安装后可使用 `airt` 命令行入口。

## 配置

复制 [`config.example.yaml`](config.example.yaml)，然后通过环境变量提供凭据，不要把 API Key 直接写进配置文件：

```bash
export TARGET_API_KEY="..."
export JUDGE_API_KEY="..."
```

被测目标可为兼容 OpenAI `/v1/chat/completions` 的应用，也可为原生 Dify Chat API 应用。OpenAI 兼容目标使用 `target.provider: openai_compatible`（未写 provider 时也默认该值）。Dify 使用 `target.provider: dify`，并请求 `{base_url}/chat-messages`（通常配置 `base_url: https://dify.example.com/v1`，实际端点为 `/v1/chat-messages`）。默认纯文本 Dify 目标使用 `response_mode: blocking`；独立 Agent profile 可显式设置 `response_mode: streaming` 和 `capture_tool_calls: true`，以采集 Dify `agent_thought` 工具调用观测。

通过只切换 YAML 中的 `target.provider` 和相应字段即可使用同一个 `airt run` 命令，无需修改源代码。Dify 配置不需要 `model`：使用 `${DIFY_AGENT_API_KEY}`、`inputs: {}` 和稳定的 `user_prefix`。Chatflow 使用独立的 `config.dify.agent.yaml`，顶层 target 已配置 streaming 工具观测，日常命令无需再写 `--target-profile agent`；`--target-profile` 仍保留给多目标高级配置。Dify 应用的实际系统提示词必须在 Dify 控制台中配置；在 `airt` 配置中保存一份**与 Dify 应用匹配的 `system_prompt` 副本仅用于泄露检测**，该文本不会被作为 Dify `query` 发送。

可选的独立裁判模型（judge）可以使用其他 OpenAI 兼容服务（包括 Qwen、DeepSeek），也可以使用官方 Anthropic API。Judge 的规范输出为攻击目标达成时 `success`、被阻止或未达成时 `fail`；为了兼容部分安全 Judge 的常见响应，外部 `pass` 会被安全地转换为内部 `fail`，其他未知 verdict 仍会作为结构化响应错误处理。OpenAI 兼容 Judge 的瞬时超时、网络错误、408、429 和 5xx（包括 524）会按 `judge.retries` 有界重试；`run.retries` 只重试被测目标请求，400、认证错误和结构化输出错误不会重试。

通过 `judge.provider` 指定裁判提供商：

- `openai_compatible`：适用于 Qwen、DeepSeek 和其他 OpenAI 兼容服务；
- `anthropic`：适用于官方 Anthropic API。使用该选项时，请配置 Claude 模型，例如 `claude-opus-5`，以及对应的 Anthropic API 地址。

目标与裁判必须使用彼此独立的凭据。API Key 仅支持通过 `${TARGET_API_KEY}`、`${DIFY_AGENT_API_KEY}` 和 `${JUDGE_API_KEY}` 这类环境变量引用传入。

## CLI 使用流程

不访问任何 API，列出默认的无害测试用例：

```bash
airt list --cases cases
airt list --cases cases --include-sensitive
```

执行一次已配置的评估。当前主目标是 Dify Chatflow，只保留 `security`、`quality`、`release` 三个运行档位；`chatflow assess` 是一次执行安全 + 质量的组合命令。`--out` 只指定可续跑的 `results.jsonl` 保存目录，最新报告写入运行命令所在目录的 `reports/<mode>/`。

```bash
airt chatflow security
airt chatflow quality
airt chatflow release
airt chatflow assess --out runs/chatflow-assess
```

普通运行会先覆盖指定输出目录中的旧 `results.jsonl`，因此只统计本次结果；只有 `--resume` 才会保留旧 JSONL、跳过已完成用例并续跑。显式 `--out` 仅用于按项目或批次隔离 JSONL 运行状态；每次完成后都会刷新对应模式下的 `reports/<mode>/report.json` 和 `reports/<mode>/report.html`。同时，每一次 `airt run` 或离线 `airt report` 都会把当时用于渲染的完整 JSONL、JSON 报告和 HTML 报告保存到不可覆盖的 `reports/<mode>/archive/<UTC时间戳>/`。归档不会自动清理；查看历史结果时直接打开对应归档目录中的 `report.html`。

统一 Chatflow 使用 `config.dify.agent.yaml` 和 `DIFY_AGENT_API_KEY`。工具安全、知识库质量、发布门禁分别使用上面的快捷命令；`chatflow assess` 会把安全和质量原始结果分开写入 `security/`、`quality/` 子目录，并把完整综合报告写入 `reports/assess/` 及其 `archive/`。

只有显式指定 `--include-sensitive` 才会加载 `cases/sensitive/` 下的文件。`--resume` 会跳过 `results.jsonl` 中已完成的用例 ID；传输层错误保留为 `error` 状态，可在后续运行时重新尝试。

风险分阈值在加权风险分低于指定值时失败；严重级别阈值在存在达到该级别或更高且攻击成功的用例时失败。退出码 `1` 表示阈值违反，退出码 `2` 表示输入或配置无效。

从已有 JSONL 文件离线重新生成报告。省略 `--out` 时根据 JSONL 中记录的运行模式写入当前工作目录的 `reports/<mode>/`；没有运行元信息的旧 JSONL 默认归入 `reports/quality/`。传入 `--out` 可导出到指定报告目录：

```bash
airt report --results runs/my-run/results.jsonl --out runs/my-run
```

每种报告开头都会显示测试类型和测试方式；HTML 和终端报告使用中文的人类可读展示，逐条呈现测试请求、模型回复和判定结论。`report.json` 与 `results.jsonl` 保持结构化机器可读格式，适用于 CI、自动分析和审计。`success` 始终表示攻击成功，`fail` 表示攻击未成功；这些元信息会持久化在每条新结果中。对没有元信息的旧 JSONL，`airt report` 仍可离线生成报告，并明确显示 `Not recorded in original results (legacy JSONL)`，不会伪造运行信息。

报告输出目录包含：

```text
reports/
├── security/
├── quality/
└── release/
    ├── report.json
    ├── report.html
    └── archive/<UTC时间戳>/
```

`report` 和 `list` 命令不会创建 API 客户端，也不会发送网络请求。报告会对疑似敏感字段脱敏，且不会包含配置中的 API Key 或 Authorization 请求头。

默认测试套件完全离线。真实适配器冒烟测试为显式启用模式，只有在已为授权测试端点设置以下三个变量时才会运行：

```bash
AIRT_LIVE_BASE_URL=...
AIRT_LIVE_API_KEY=...
AIRT_LIVE_MODEL=...
python -m pytest -m live -q
```

内置用例库覆盖以下类别：

- Prompt 注入
- 间接 Prompt 注入
- 越狱
- 角色扮演
- 编码混淆
- 目标劫持
- 数据外带

默认用例使用无害代理目标。将组织特定的敏感 payload 放在 `cases/sensitive/` 下，并在启用前确认已经取得测试授权。

## 授权与安全

只能测试你拥有或已获得明确授权进行安全评估的 LLM 应用。本项目默认使用无害代理目标进行非破坏性测试。不得使用本工具发送未授权请求，或进行现实世界中的有害操作。`airt --help` 也会显示相同的授权提示。


## 推荐快捷命令

```powershell
# Chatflow 工具安全，默认调用安全 Judge
.\.venv\Scripts\airt.exe chatflow security

# Chatflow 安全 + 质量，一键执行
.\.venv\Scripts\airt.exe chatflow assess

# 仅质量评测
.\.venv\Scripts\airt.exe chatflow quality

# 发布前门禁
.\.venv\Scripts\airt.exe chatflow release

# 只检查配置
.\.venv\Scripts\airt.exe doctor --mode quality
```

旧的 `airt text ...` 纯文本命令以及 `rules`、`balanced` 档位已删除。需要脚本化或自定义用例时，使用 `airt run --config ... --cases ... --mode security|quality|release`。

## 工程化能力

项目额外提供离线用例校验、运行 ID/失败分类、历史趋势和静态 Dashboard：

```powershell
.\.venv\Scripts\airt.exe cases validate shared_cases/unified_chatflow.yaml
.\.venv\Scripts\airt.exe trend --reports reports/quality
.\.venv\Scripts\airt.exe dashboard --reports reports
```

GitHub Actions 会自动运行测试、校验共享用例，并将报告和 Dashboard 上传为构建 artifact。

启用 GitHub Actions 的实时 Chatflow 测试还需要配置 `DIFY_BASE_URL`。它必须是 GitHub runner 可访问的 Dify API 地址（带 `/v1`）；本机 Docker 地址 `http://127.0.0.1/v1` 只能用于本地运行，不能用于 GitHub runner。
