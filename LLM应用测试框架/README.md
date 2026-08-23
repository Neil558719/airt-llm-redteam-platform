# llmtest —— LLM 应用自动化测试框架

给大模型应用（聊天机器人 / RAG 助手）做**自动化测试**与**质量评估**的一体化框架，基于 pytest 封装。

## 特性

- **四类基础断言**
  - 语义断言 `assert_semantic_match` —— 回答含义与期望等价（支持换述）
  - 相似度断言 `assert_similarity` —— 文本向量余弦相似度
  - JSON Schema 校验 `assert_valid_json` / `assert_json_schema` —— 结构化输出校验
  - LLM-as-Judge `assert_llm_judge` —— 按细则自动打分
- **幻觉检测模块**：把回答分解为事实断言，逐条与 RAG 上下文核对，计算**幻觉率**
- **质量报告看板**：自动生成自包含 HTML，展示准确率 / 幻觉率 / 响应延迟等指标与图表
- **双模式**：`mock` 模式零依赖、确定性、无需 API key，开箱即跑；`real` 模式接真实模型（OpenAI 兼容 / Anthropic）

## 安装

```bash
pip install -e .          # 基础（Mock 模式 + 测试）
pip install -e ".[real]"  # 加上真实模型 SDK（openai / anthropic）
```

## 快速开始（Mock 模式）

```bash
pytest tests/ -v
```

跑完后自动生成 `reports/llm_test_report.html`，浏览器打开即可查看质量看板。

`tests/` 套件是**双模式**的：`pytest tests/` 用 Mock（确定性、无需 key）做快速回归；
同一套用例也能直接切到真实模型：

```bash
pytest tests/ \
    --app-model deepseek-v4-flash --app-api-key $DEEPSEEK_API_KEY \
    --llm-mode real --llm-provider openai --llm-model gpt-5.6-sol --llm-api-key $KEY
```

> 真实模式下：语义/Judge/幻觉/JSON 都走 LLM，正常可用；`assert_similarity` 需要网关提供
> Embedding 接口（如 `text-embedding-3-small`）。这是**框架级能力**：任何项目里，若评测客户端
> 没有可用的 embedding 模型，`assert_similarity` 都会**自动跳过**（pytest.skip），而不是让用例失败；
> Mock 模式用确定性伪向量始终能测。语义断言可替代它判断"意思相近"。

## 编写用例

```python
# test_my_app.py
from llmtest import (
    assert_semantic_match, assert_similarity,
    assert_valid_json, assert_json_schema,
    assert_llm_judge, assert_hallucination_rate, JudgeSpec,
)

def test_answer_correct(app_under_test, llm_client):
    resp = app_under_test.complete([{"role": "user", "content": "什么是 RAG？"}])
    assert_semantic_match(resp, "检索增强生成，结合检索与生成", client=llm_client)

def test_json_schema(app_under_test):
    data = assert_valid_json(app_under_test.complete([{"role": "user", "content": "返回 JSON"}]))
    assert_json_schema(data, {"type": "object", "required": ["name"]})

def test_judge_score(app_under_test, llm_client):
    resp = app_under_test.complete([{"role": "user", "content": "你好"}])
    assert_llm_judge(resp, JudgeSpec.helpfulness(), min_score=60, client=llm_client)

def test_no_hallucination(app_under_test, llm_client):
    result = app_under_test.ask("问题")   # 结构化回答：answer + sources（应用检索到的上下文）
    assert_hallucination_rate(result.answer, result.sources, max_rate=0.4, client=llm_client)
```

- `app_under_test`：你的被测应用。Mock 模式下框架提供模拟；真实场景替换为你自己的调用入口。
  - `app_under_test.complete(...)`：普通对话，返回文本。
  - `app_under_test.ask(question)`：RAG 式提问，返回 `AppResponse(answer, sources)`——
    `sources` 是应用生成时真正参考的检索结果，幻觉检测用它核对事实。
- `llm_client`：框架内置评测客户端（语义 / 相似度 / Judge / 幻觉判定）。
- `assert_llm_judge(..., question="原题")`：评判**准确性/相关性**时，把产生回答的用户问题传上，
  裁判才能核对答案是否正确（例如数学题不传原题，它无法判断 "391" 对不对）；纯质量维度（有用性）可不传。
- 断言失败抛 `AssertionError`，附带实际分数、阈值与理由，并自动记录到报告。

## 真实模式

通过环境变量或 pytest 参数切换：

```bash
# OpenAI 兼容（OpenAI / DeepSeek / 通义千问 / Moonshot / vLLM …）
export LLM_TEST_MODE=real LLM_PROVIDER=openai
export LLM_API_KEY=sk-xxx LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-chat
pytest tests/ -v --llm-model deepseek-chat

# Anthropic
export LLM_TEST_MODE=real LLM_PROVIDER=anthropic
export LLM_API_KEY=sk-ant-xxx
pytest tests/ -v
```

> 优先级：pytest 命令行参数 > 环境变量 > 默认值。API key 建议用环境变量 `LLM_API_KEY`，避免出现在命令历史。

## 被测对象 vs 裁判（两个角色）

框架里有两个容易混淆的角色，**它们应当分开、各自独立配置**：

| | 被测对象（App under test） | 裁判（`llm_client`） |
|---|---|---|
| 是谁 | 你要测的应用：客服 App / Chatbot / RAG 助手；**也可以是裸模型** | 框架用来评估回答质量的**独立模型** |
| 干什么 | 产生回答（answer + sources） | 给回答打分 / 判幻觉 / 判语义 |
| 怎么配置 | `--app 名字`（注册 App）或 `--app-model <模型>`（裸模型） | 真实模式：`--llm-mode/--llm-provider/--llm-model` |
| 为什么分开 | —— | 裁判不能是"被测自己"，否则等于自己给自己打分（自评偏差，分常虚高） |

**没有真实 App？直接把模型当被测对象，不用改代码：**

```bash
pytest examples/model_vs_model/ \
    --app-provider deepseek --app-model deepseek-chat --app-api-key $DEEPSEEK_API_KEY \
    --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY
```

被测模型支持 `openai / anthropic` 及别名 `deepseek / qwen / zhipu / moonshot / ollama / local`
（框架自动补默认 base_url），裁判同理，见 [`examples/model_vs_model/`](examples/model_vs_model/)。

**被测 App 怎么接**：写一个适配器，把它包成 `ask(question) -> AppResponse(answer, sources)`，
所有断言即可复用。完整示例见 [`examples/customer_service/`](examples/customer_service/)：

```python
from llmtest import AppResponse, register_app, track_latency
import requests

class CustomerServiceApp:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
    def ask(self, question, user_id=None):
        with track_latency():                      # 真实调用耗时自动进看板
            resp = requests.post(f"{self.base_url}/chat",
                                 json={"question": question},
                                 headers={"Authorization": f"Bearer {self.api_key}"})
        data = resp.json()
        return AppResponse(answer=data["reply"], sources=data.get("citations", []))

@register_app("cs")                                 # 注册被测对象
def _build_cs():
    return CustomerServiceApp(base_url=os.environ["CS_BASE_URL"], api_key=os.environ["CS_API_KEY"])
```

**现成完整示例：Dify 知识库客服机器人**（`examples/dify_bot/`，**10 条用例覆盖 9 个评测维度**）——
Dify 的对话接口天然返回 `answer` + 检索到的知识片段，适配器把片段映射成 `AppResponse.sources`，
幻觉检测即用机器人**真实看到的知识**核对；另覆盖换述鲁棒性、知识库外拒答、相关性打分、
多轮会话、**批量问题集回归**等企业客服场景。报告内置**历史运行对比**表；配套
`compare_judges.py` 做**双裁判模型一致性**体检（各裁判可独立 key，自动生成 `reports/judge_compare.html`）。用例讲解见术语手册 3.5c/3.5d；部署 + 建知识库 +
迁移到另一台电脑的指引见 [`docs/Dify 部署与迁移指南.md`](docs/Dify 部署与迁移指南.md)。
```

## 使用手册：切换被测模型 / 裁判模型

被测对象与裁判**互相独立**，各自用一条命令切换，测试代码一行都不用改。
切换只改「谁被问」（被测）和「谁来评」（裁判）两个角色。

> 下文命令为 **bash 语法**（Git Bash / WSL / Linux / macOS 通用）。Windows 用户若用
> **PowerShell**，请把 `export VAR=值` 换成 `$env:VAR = "值"`、`\` 续行换成 `` ` `` 或不换行，
> 具体见文末「PowerShell 版」。

### 角色与参数速查

| 角色 | 命令行参数 | 环境变量 |
|---|---|---|
| **被测模型**（裸模型当被测对象） | `--app-model` `--app-provider` `--app-base-url` `--app-api-key` | `LLM_APP_MODEL` `LLM_APP_PROVIDER` `LLM_APP_BASE_URL` `LLM_APP_API_KEY` |
| **被测 App**（注册的真实应用） | `--app <注册名>` | `LLM_APP` |
| **裁判模型** | `--llm-mode` `--llm-provider` `--llm-model` `--llm-base-url` `--llm-api-key` | `LLM_TEST_MODE` `LLM_PROVIDER` `LLM_MODEL` `LLM_BASE_URL` `LLM_API_KEY` |

> `--app-provider` 与 `--llm-provider` 接受相同的一组提供商别名，见下方「支持的提供商」。

### 支持的提供商（被测 / 裁判通用）

传 `--app-provider` / `--llm-provider` 时，框架自动补默认接口地址，不用手写 `--*-base-url`：

| 别名 | 客户端 | 默认 base_url |
|---|---|---|
| `openai` | OpenAI 兼容 | 官方默认接口 |
| `anthropic` | Anthropic（Claude） | — |
| `deepseek` | OpenAI 兼容 | `https://api.deepseek.com` |
| `qwen` | OpenAI 兼容 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `zhipu` | OpenAI 兼容 | `https://open.bigmodel.cn/api/paas/v4` |
| `moonshot` | OpenAI 兼容 | `https://api.moonshot.cn/v1` |
| `ollama` | OpenAI 兼容 | `http://localhost:11434/v1`（本地） |
| `local` | OpenAI 兼容 | `http://localhost:8000/v1`（vLLM 等本地部署） |

任意 OpenAI 兼容服务（包括公司内网网关、私有部署）：
用 `--*-provider openai --*-base-url <你的地址> --*-model <模型名>` 即可。

### 常用场景（可直接复制）

> 每个场景同时给出 **bash**（Git Bash / WSL / macOS / Linux）与 **PowerShell 单行**（Windows）两种写法。
> PowerShell 里 `$env:KEY` 表示从环境变量取 key；没设对应环境变量时，直接把它换成实际的 key 字符串即可。

**场景 1 · 被测 = DeepSeek，裁判 = Claude**（最典型的「跨厂商」组合）

```bash
pytest examples/model_vs_model/ \
    --app-provider deepseek --app-model deepseek-chat --app-api-key $DEEPSEEK_API_KEY \
    --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY
```

```powershell
pytest examples/model_vs_model/ --app-provider deepseek --app-model deepseek-chat --app-api-key $env:DEEPSEEK_API_KEY --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $env:ANTHROPIC_API_KEY
```

**场景 2 · 被测 = OpenAI，裁判 = Claude**

```bash
pytest examples/model_vs_model/ \
    --app-provider openai --app-model gpt-4o --app-api-key $OPENAI_API_KEY \
    --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY
```

```powershell
pytest examples/model_vs_model/ --app-provider openai --app-model gpt-4o --app-api-key $env:OPENAI_API_KEY --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $env:ANTHROPIC_API_KEY
```

**场景 3 · 被测 = DeepSeek，裁判 = OpenAI**

```bash
pytest examples/model_vs_model/ \
    --app-provider deepseek --app-model deepseek-chat --app-api-key $DEEPSEEK_API_KEY \
    --llm-mode real --llm-provider openai --llm-model gpt-4o --llm-api-key $OPENAI_API_KEY
```

```powershell
pytest examples/model_vs_model/ --app-provider deepseek --app-model deepseek-chat --app-api-key $env:DEEPSEEK_API_KEY --llm-mode real --llm-provider openai --llm-model gpt-4o --llm-api-key $env:OPENAI_API_KEY
```

**场景 4 · 被测 = 本地 Ollama，裁判 = OpenAI**

```bash
pytest examples/model_vs_model/ \
    --app-provider ollama --app-model qwen2.5:7b \
    --llm-mode real --llm-provider openai --llm-model gpt-4o-mini --llm-api-key $OPENAI_API_KEY
```

```powershell
pytest examples/model_vs_model/ --app-provider ollama --app-model qwen2.5:7b --llm-mode real --llm-provider openai --llm-model gpt-4o-mini --llm-api-key $env:OPENAI_API_KEY
```

**场景 5 · 被测 = 任意 OpenAI 兼容服务（vLLM / 企业网关），裁判 = OpenAI**

```bash
pytest examples/model_vs_model/ \
    --app-provider openai --app-base-url http://localhost:8000/v1 --app-model YOUR_MODEL --app-api-key $KEY \
    --llm-mode real --llm-provider openai --llm-model gpt-4o --llm-api-key $OPENAI_API_KEY
```

```powershell
pytest examples/model_vs_model/ --app-provider openai --app-base-url http://localhost:8000/v1 --app-model YOUR_MODEL --app-api-key $env:KEY --llm-mode real --llm-provider openai --llm-model gpt-4o --llm-api-key $env:OPENAI_API_KEY
```

**场景 6 · 被测 = 注册的真实 App，裁判 = Claude**

```bash
pytest --app cs \
    --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $ANTHROPIC_API_KEY
```

```powershell
pytest --app cs --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key $env:ANTHROPIC_API_KEY
```

**场景 7 · 全 Mock 快速验证**（无需任何 API key，最快最稳；bash / PowerShell 通用）

```bash
pytest tests/          # 被测 = mock-cs（Mock），裁判 = Mock
```

### 只切换一侧

```bash
# 被测不变，只换裁判（换成 qwen 官网：阿里云百炼 DashScope，key 也要换成 DashScope 的）
pytest examples/model_vs_model/ --llm-mode real --llm-provider qwen --llm-model qwen-max --llm-api-key $DASHSCOPE_API_KEY

# 裁判不变，只换被测
pytest examples/model_vs_model/ --app-provider qwen --app-model qwen-max --app-api-key $QWEN_API_KEY
```

```powershell
# 被测不变，只换裁判（换成 qwen 官网：阿里云百炼 DashScope，key 也要换成 DashScope 的）
pytest examples/model_vs_model/ --llm-mode real --llm-provider qwen --llm-model qwen-max --llm-api-key $env:DASHSCOPE_API_KEY

# 裁判不变，只换被测
pytest examples/model_vs_model/ --app-provider qwen --app-model qwen-max --app-api-key $env:QWEN_API_KEY
```

> **换 provider = 换服务商，key 必须跟着换**：`qwen` 走阿里云百炼，要用 DashScope 的 key；
> 公司网关的 key 只对网关内的模型有效。模型名以对应平台控制台为准（如 `qwen-max`/`qwen-plus`/`qwen-turbo`）。

### 环境变量方式（export 一次，命令最短）

```bash
export LLM_APP_PROVIDER=deepseek
export LLM_APP_MODEL=deepseek-chat
export LLM_APP_API_KEY=$DEEPSEEK_API_KEY
export LLM_TEST_MODE=real
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-opus-5
export LLM_API_KEY=$ANTHROPIC_API_KEY

pytest examples/model_vs_model/        # 一行搞定
```

> 优先级：**命令行参数 > 环境变量 > 默认值**。命令参数只覆盖该次运行；环境变量适合长期默认。
> API key 建议用环境变量，避免出现在 shell 历史里。

### PowerShell 版（Windows）

上面是 bash 语法。Windows 自带的 PowerShell 写法如下（`$env:变量 = 值`）：

```powershell
# 被测模型 = DeepSeek
$env:LLM_APP_PROVIDER = "deepseek"
$env:LLM_APP_MODEL = "deepseek-chat"
$env:LLM_APP_API_KEY = "sk-deepseek-你的key"

# 裁判模型 = Claude
$env:LLM_TEST_MODE = "real"
$env:LLM_PROVIDER = "anthropic"
$env:LLM_MODEL = "claude-opus-5"
$env:LLM_API_KEY = "sk-ant-你的key"

# 跑测试
pytest examples/model_vs_model/
```

不想设环境变量，直接用命令行参数（PowerShell 里写一整行，key 直接填或用 `$env:XXX` 引用）：

```powershell
pytest examples/model_vs_model/ --app-provider deepseek --app-model deepseek-chat --app-api-key "sk-deepseek-你的key" --llm-mode real --llm-provider anthropic --llm-model claude-opus-5 --llm-api-key "sk-ant-你的key"
```

> bash ↔ PowerShell 对照：`export A=B` ↔ `$env:A = "B"`；`$VAR` ↔ `$env:VAR`；`\` 续行 ↔ `` ` `` 或不换行。
> 在 **Git Bash** 里跑则直接用上面的 bash 命令即可。

### 优先级规则

- **被测对象**：`--app <注册名>` > `--app-model <裸模型>` > 注册默认应用 > Mock 兜底
- **裁判**：始终由 `--llm-*` 参数（或 `LLM_*` 环境变量）决定；不给则默认 Mock

### 三个提醒

1. **模型 ID 以平台为准**：`deepseek-chat`、`claude-opus-5`、`gpt-4o` 是常见写法，具体以各家控制台为准；
   写错会返回 `model not found`。`qwen2.5:7b` 是 Ollama 的模型标签。
2. **裁判用 Anthropic 时**：语义断言、Judge、幻觉检测走 LLM 完全正常；但 Anthropic 没有原生
   Embedding 接口，相似度断言（`assert_similarity`）会回退为关键词覆盖伪向量并打印一次警告。
   需要精确向量相似度时，裁判改用 OpenAI 兼容提供商。
3. **裸模型当被测对象时没有检索来源**（`sources` 为空），幻觉检测需要把上下文写进 prompt、
   再显式传同一份上下文来核对（见 `examples/model_vs_model/test_model.py`）。

## CLI 选项

| 选项 | 说明 |
| --- | --- |
| `--llm-mode mock\|real` | 裁判运行模式（默认 mock） |
| `--llm-provider P` | 裁判提供商：`openai`/`anthropic` 或别名 `deepseek`/`qwen`/`zhipu`/`moonshot`/`ollama`/`local` |
| `--llm-model MODEL` | 裁判模型名 |
| `--llm-base-url URL` | 裁判 OpenAI 兼容 base_url |
| `--llm-api-key KEY` | 裁判 API key（推荐用环境变量） |
| `--app NAME` | 被测对象 = 注册的应用（`register_app` 注册） |
| `--app-model MODEL` | 被测对象 = 裸模型（被测模型的模型名） |
| `--app-provider P` | 被测模型提供商（同 `--llm-provider` 别名） |
| `--app-base-url URL` | 被测模型 OpenAI 兼容 base_url |
| `--app-api-key KEY` | 被测模型 API key |
| `--report PATH` | 报告输出路径（默认 `reports/llm_test_report.html`） |
| `--no-report` | 不生成报告 |
| `--no-history` | 不保留历史报告归档（默认每次会归档 + 更新 `reports/index.html`） |

> 被测侧环境变量前缀 `LLM_APP_`（`LLM_APP_MODEL`/`LLM_APP_PROVIDER`/`LLM_APP_BASE_URL`/`LLM_APP_API_KEY`）；
> 裁判侧 `LLM_*`（`LLM_MODEL`/`LLM_PROVIDER`/`LLM_TEST_MODE`/`LLM_API_KEY`）。

## 报告看板

- **hero 指标**：通过率、准确率（LLM-as-Judge 平均）、幻觉率、平均响应延迟
- **图表**：幻觉率（按状态色分档）、响应延迟、Judge 分数（均为 SVG，离线可用）
- **用例明细**：每个用例的状态、耗时、延迟、幻觉率、Judge 分、断言记录，可展开查看失败信息与幻觉逐条判定
- **历史归档**：每次运行保留一份时间戳副本（`llm_test_report_<时间>.html`），并更新
  `reports/index.html` 历史索引页，按时间倒序展示每次运行的通过/失败与「被测·裁判」，方便回归对比
- 支持明暗模式切换
- 用 `--no-history` 可关闭历史归档

## 架构

```
llmtest/
├── config.py          # 配置（env / pytest 参数）
├── apps.py            # 被测应用注册表（@register_app + --app 切换被测对象）
├── clients/           # LLM 客户端：base(抽象) / mock / openai / anthropic
├── assertions/        # assert_semantic_match / assert_similarity / assert_valid_json
│                      # / assert_json_schema / assert_llm_judge
├── hallucination/     # detect_hallucination / assert_hallucination_rate（幻觉率）
├── judge/             # llm_judge + JudgeSpec 预设细则
├── metrics/           # 指标采集（延迟 / 幻觉率 / Judge 分 → 用例记录）
├── reporting/         # 自包含 HTML 报告 + SVG 图表看板
├── plugin.py          # pytest 插件（选项、结果采集、会话结束出报告）
└── fixtures.py        # llm_client / llm_config / app_under_test / record_metric
```

## 目录

```
tests/conftest.py           # 双模式：注册 mock-cs；--app-model 可切真实模型
tests/test_chatbot.py       # 聊天机器人：语义 / 相似度 / JSON / Judge（Mock 与真实模型通用）
tests/test_rag_assistant.py # RAG 助手：幻觉检测 / 延迟（上下文写进 prompt，双模式通用）
examples/customer_service/  # 接入真实客服 App：adapter + 注册 + 示例用例
examples/dify_bot/          # 接入 Dify 知识库客服机器人：adapter + probe + 用例 + question_bank + 双裁判脚本
examples/model_vs_model/    # 模型对模型（精简版）：只测模型，全终端切换
examples/kb_bots/           # 多平台共享套件：一套用例一条命令测 Dify / FastGPT
examples/kb_bots/data/      # 数据驱动问题集（knowledge_questions.json）
scripts/ci_run.py           # CI 脚本：一条命令跑两档（Mock 冒烟 + 真实回归）
scripts/probe_embedding.py  # 诊断脚本：探测网关 Embedding 可用性
docs/术语手册与原理详解.md        # 术语 + 原理 + 用例全解
docs/使用手册.md                  # 完整功能 + 运行方法（不遗漏）
docs/Dify 部署与迁移指南.md       # Dify 部署 · 接入 · 迁移
docs/FastGPT 部署与迁移指南.md    # FastGPT 部署 · 接入 · 迁移
docs/迁移说明.md                  # 迁移到新电脑 / Python 3.14 兼容 / GitHub 上传
CHANGELOG.md                      # 开发记录 + 遇到的问题
reports/llm_test_report.html        # 最新报告（历史摘要见 history.json）
reports/judge_compare.html          # 双裁判对比报告
```
