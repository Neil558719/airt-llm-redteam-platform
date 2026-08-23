# Dify 客服机器人：部署 · 接入 · 迁移指南

> 目标：在本机搭一个真实的企业知识库客服机器人（Dify + 知识库 RAG），接入 llmtest 做质量测试，
> 并且**整个项目（框架 + Dify + 知识库）能完整迁移到另一台电脑**。
>
> 被测对象 = Dify 机器人（自带知识库 + 生成模型）；裁判 = 框架的 `--llm-*`（独立模型）。
> 两者分离，符合「被测 vs 裁判」架构（见术语手册 3.6）。

---

## 0. 总体架构

```
┌─ 被测对象 ──────────────────────────────┐   ┌─ 裁判（独立）────────────┐
│  Dify 客服机器人                        │   │  --llm-*（如 gpt-5.6-sol）│
│   ├─ 知识库（退货政策文档，向量化检索）  │   └──────────┬───────────────┘
│   └─ 生成模型（公司网关 deepseek）       │              │ 打分/判幻觉/判语义
│        ▲  answer + 检索到的 sources       │              │
└────────┼────────────────────────────────┘              │
         │ examples/dify_bot/adapter.py（ask → AppResponse）│
         └───────────────────────────────────┼─────────────┘
                                             ▼
                                     pytest 断言 + 报告看板
```

- **幻觉检测用 `result.sources`**：Dify 对话接口会返回它检索到的知识片段
  （`retriever_resources`），适配器映射成 `AppResponse.sources`。核对对象 = 机器人
  **真实看到的知识**，这是生产级做法，比测试方编资料更可信（术语手册 4.4「上下文」）。
- **embedding 约束**：Dify 知识库向量化需要 embedding 模型。⚠️ 公司网关
  `newapi.gosuncn.com` **没有 embedding 接口**，所以 Dify 里不能把 embedding 配成公司网关。
  推荐用本地 **Ollama + bge-m3**（免费、离线、迁移友好），见第 2 节。

---

## 1. Dify 本地 Docker 部署（Windows）

前置：安装 **Docker Desktop**（开启 WSL2 backend），内存建议 ≥ 8GB。

```bash
# 1) 下载 Dify（任意目录）
git clone https://github.com/langgenius/dify.git
cd dify/docker

# 2) 生成配置
cp .env.example .env

# 3) 启动（首次拉镜像较久，耐心等）
docker compose up -d

# 4) 浏览器打开 http://localhost/install 初始化管理员账号
```

启动后 `docker ps` 应有多个容器（api / web / worker / postgres / redis / 向量库 /
sandbox / nginx…），全部 running 即可。

> 云版备选：不想装 Docker，用 [cloud.dify.ai](https://cloud.dify.ai)（base_url =
> `https://api.dify.ai/v1`）。迁移策略不变（仍用 DSL + 知识库导出，见第 6 节）。

---

## 2. 配置模型供应商（关键步骤）

Dify 需要两类模型：**LLM**（生成回答）+ **Embedding**（知识库向量化）。

### 2.1 LLM —— 用公司网关（OpenAI 兼容）

Dify 设置 → 模型供应商 → **OpenAI-API-compatible**：

| 配置 | 值 |
|---|---|
| 基础地址 | `https://newapi.gosuncn.com/v1` |
| API Key | 你的网关 key |
| 模型（用于机器人） | `deepseek-v4-flash`（或网关里任一聊天模型） |

这样机器人的"大脑"就是公司网关模型，符合"被测对象"角色。

### 2.2 Embedding —— 本地 Ollama + bge-m3（推荐）

公司网关没有 embedding，用本地免费的方案：

```bash
# 1) 安装 Ollama（https://ollama.com/download/windows），然后拉模型：
ollama pull bge-m3
```

Dify 设置 → 模型供应商 → **Ollama**：

| 配置 | 值 |
|---|---|
| 基础地址 | `http://host.docker.internal:11434`（Dify 是容器，用它访问宿主机 Ollama） |
| Embedding 模型 | `bge-m3` |

> 为什么不用云 embedding？迁移时云服务要配新 key；Ollama 是本地模型，
> 新电脑装 Ollama 拉同一个模型即可，**不依赖任何第三方账号**，最符合"完整迁移"目标。

---

## 3. 建知识库（退货 / 售后政策）

1. Dify → **知识库** → 创建知识库；
2. 上传现成文档：**`examples/dify_bot/knowledge/knowledge_base.md`**（多主题客服知识库：
   退货 / 换货 / 退款 / 物流 / 发票 / 积分 / 会员 / 保修等，检索区分度高、测试更稳定），
   索引方式选「高质量」，Embedding 模型选第 2.2 节的 `bge-m3`；
3. 等待索引完成（文档状态变绿）。

> 这份知识库文档放在项目里，跟着仓库走——迁移到新电脑时直接用它重建知识库，无需重新编写。

---

## 4. 建应用并生成 API Key

1. Dify → **创建应用** → 类型选 **Chatbot**（对话型）；
2. 编排：**上下文**里挂上第 3 节的知识库；系统提示词建议：
   > 你是公司客服助手。请只根据提供的知识库内容回答，资料里没有的就如实说不知道，不要编造。
3. 右上角 **发布**；
4. 打开 **访问 API** 页 → 创建 **API 密钥**（形如 `app-xxx`）。

记下两个值（迁移时要带着）：
- API 地址：`http://localhost/v1`
- API 密钥：`app-xxx`

---

## 5. 接入 llmtest 并测试

```powershell
# 1) 设环境变量（当前 PowerShell 窗口）
$env:DIFY_BASE_URL = "http://localhost/v1"
$env:DIFY_API_KEY  = "app-xxx"

# 2) 先探针：验证 key + 看 Dify 实际返回结构（确认 retriever_resources）
python examples/dify_bot/probe_dify.py "退货期限是几天？"

# 3) 跑测试（被测 = Dify 机器人，裁判 = 公司网关 gpt-5.6-sol）
pytest examples/dify_bot/ --app dify `
  --llm-mode real --llm-provider openai --llm-base-url https://newapi.gosuncn.com/v1 `
  --llm-model gpt-5.6-sol --llm-api-key $env:DEEPSEEK_API_KEY
```

> **key 的分工（重要）**：被测 DeepSeek 的 key 早已在 **Dify 平台内**（设置 → 模型供应商）配好，
> Dify 机器人内部自己用它调用模型。pytest 这边**只需要裁判 gpt-5.6-sol 的 key**（`--llm-api-key`），
> 不需要被测的 key——这正是"被测 vs 裁判分离"的体现：被测的认证封装在 Dify 里，框架只碰裁判。

预期（**10 条用例，9 个评测维度**，逐条讲解见术语手册 3.5c / 3.5d）：
- 语义断言 ×2（正常提问 + 换述口语化问法）、Judge ×2（准确性 + 相关性）、
  JSON、延迟、多轮会话 → 通过；
- 幻觉检测用 Dify 真实检索的 `sources` 核对，忠实作答则幻觉率低 → 通过；
- 知识库外拒答 → 回答须表达"没有该信息"、不编造 → 通过；
- 批量问题集回归 → 一篮子 7 个常见问题整体通过率 ≥ 80% → 通过。

报告自动写到 `reports/`，并在报告内展示「历史运行对比」表。

---

## 5.5 进阶能力：批量回归 · 历史对比 · 双裁判对比

Dify 接入打通后，三个工程化能力直接可用（原理详见术语手册 3.5d）。

### 5.5.1 批量问题集回归（第 10 条用例）

一篮子常见问题一次跑完，整体通过率须 ≥ 80%，失败逐条列出问题与裁判理由：

```powershell
pytest examples/dify_bot/test_dify_bot.py::test_dify_question_bank_regression --app dify --llm-mode real --llm-provider openai --llm-base-url https://newapi.gosuncn.com/v1 --llm-model gpt-5.6-sol --llm-api-key $env:DEEPSEEK_API_KEY
```

问题集在 `examples/dify_bot/question_bank.py`，按你的知识库增删条目即可。

### 5.5.2 历史报告对比

每次运行自动把摘要写进 `reports/history.json`，最新报告内「历史运行对比」表展示最近 20 次的
通过率 / 准确率 / 幻觉率 / 延迟 / 被测·裁判（最新在上）。**换模型或改知识库后重跑一轮**，
即可直观对比质量变化；`reports/index.html` 仍按时间浏览每份完整归档报告。

### 5.5.3 双裁判模型对比（评估裁判可靠性）

同一批回答用两个裁判模型分别打分，输出平均分差 / 皮尔逊相关 / 通过判定一致率，
并自动生成对比报告 `reports/judge_compare.html`。报告**每题可展开查看 Dify 回答与两个裁判的
打分理由**（诊断分差）；每次运行生成**时间戳归档**并写入 `judge_compare_history.json`，
最新报告内展示**历史对比记录**（不再只有最近一次）。

**网关按厂商分组、两裁判 key 不同**（如 gpt-5.6-sol 与 deepseek-v4-flash 在不同分组）：

```powershell
python examples/dify_bot/compare_judges.py --mode real --provider openai --base-url https://newapi.gosuncn.com/v1 --judge-a gpt-5.6-sol --judge-a-key sk-openai分组 --judge-b deepseek-v4-flash --judge-b-key sk-deepseek分组
```

裁判 A 换成 **qwen 官网**（阿里云百炼，用 DashScope key）同理：

```powershell
python examples/dify_bot/compare_judges.py --mode real --judge-a qwen-max --judge-a-provider qwen --judge-a-key sk-DashScope --judge-b gpt-5.6-sol --judge-b-provider openai --judge-b-base-url https://newapi.gosuncn.com/v1 --judge-b-key sk-公司网关key
```

若两裁判同网关同分组（共用一个 key），则只传公共 `--api-key` 即可。配置优先级：
裁判独立参数（`--judge-?-key / --judge-?-provider / --judge-?-base-url`）> 公共参数 > 环境变量 `LLM_*`。
**未配 real 时脚本自动降级 Mock**（不调真实模型）并打印警告。通过判定一致率 < 80% 时脚本会
提示"打分细则有歧义或裁判不可靠"，建议核查细则或换更强裁判。

---

## 6. 迁移到另一台电脑（完整 Checklist）

迁移 = **框架代码 + 环境变量 + Dify 应用 + 知识库**，四样各走各的路。

### 6.1 框架侧（拷目录 + 重装依赖）

| 步骤 | 说明 |
|---|---|
| ① 拷整个项目目录 | 含 `llmtest/` `tests/` `examples/` `docs/` `reports/` `pyproject.toml`。**不要拷 `.venv`**（跨机器失效） |
| ② 新电脑装 Python ≥3.10 | 建 venv：`python -m venv .venv` |
| ③ 装依赖 | `.venv/Scripts/pip install -e ".[real]"` |
| ④ 设环境变量 | 照 `.env.example` 填（裁判 key / Dify key / 网关地址） |
| ⑤ 冒烟 | `pytest tests/`（Mock，10 用例秒级回归，验证框架本身没问题） |
| ⑥ 接 Dify | 见 6.2，然后跑 `pytest examples/dify_bot/ --app dify ...` |

### 6.2 Dify 侧（官方 DSL + 知识库导出，官方支持的跨实例迁移格式）

| 迁移对象 | 导出 | 新机器导入 |
|---|---|---|
| 应用（提示词/工作流/引用） | 应用页 → **导出 DSL**（`.yml`） | 部署 Dify 后 → **导入 DSL** |
| 知识库内容 | 知识库 → 设置 → 导出（或直接用原始文档） | 新机器建知识库 → 导入文档 → 重建索引 |
| API 密钥 | **不随 DSL 迁移** | 新机器重新生成 `app-xxx`，更新 `DIFY_API_KEY` |
| Embedding（Ollama） | 模型本身不用迁 | 新机器装 Ollama + `ollama pull bge-m3`，Dify 里重配供应商 |

> ⚠️ Dify 的知识库在 Docker 卷里，不保证拷卷即可用；**DSL + 文档导出**是官方推荐的
> 跨实例迁移方式，换云版/换机器/换团队都通用。
> 流程顺序：先建知识库（让 DSL 里引用的知识库名存在）→ 再导入 DSL → 重新关联 → 换新 key。

### 6.3 一页速查（迁移后要更新的东西）

```
项目目录（新）            ← 拷过来，重装依赖
LLM_API_KEY               ← 裁判 key（新机器照样设）
DIFY_BASE_URL             ← 新 Dify 地址
DIFY_API_KEY              ← Dify 新生成的 app-xxx
Dify 应用                 ← 导入 DSL
Dify 知识库               ← 导入文档 + 重建索引
Ollama bge-m3             ← ollama pull bge-m3
```

---

## 7. 常见问题

- **probe 报 401**：`DIFY_API_KEY` 不是模型 key，是**应用 API 密钥**（`app-` 开头），
  在应用 → 访问 API 页生成。
- **probe 报 404 / connection refused**：`DIFY_BASE_URL` 端口不对（本地默认 `http://localhost/v1`，
  检查 `docker ps` 里 nginx 端口）。
- **sources 为空（幻觉检测跳过）**：应用没挂知识库，或索引未完成、检索没命中。
- **Dify 知识库索引失败**：embedding 模型没配好（回看第 2.2 节，Ollama 地址必须是
  `host.docker.internal`）。
- **裁判侧相似度跳过**：框架级能力——网关无 embedding 时 `assert_similarity` 自动跳过，
  不影响其它断言。
