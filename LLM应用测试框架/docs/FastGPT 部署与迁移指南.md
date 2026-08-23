# FastGPT 部署与迁移指南

> 本地 Docker 部署 FastGPT 知识库客服，接入 llmtest 做质量测试，并能完整迁移到另一台电脑。
> 与被测平台 Dify 并列，`examples/kb_bots/` 一套用例一条命令切换（`--app dify` / `--app fastgpt`）。

## 0. 硬件要求（重要）

| 内存 | 结论 |
|---|---|
| **16GB（推荐）** | Dify + FastGPT 都能舒服跑，一次一个平台 |
| **8GB（最低）** | **只能跑 Dify**；FastGPT 全家桶（code-sandbox 1GB + app 0.9GB + mongo/minio/pg）大概率 OOM/启动慢 |
| 两个平台同时跑 | ❌ 绝对不行（12GB 都爆） |

**Docker Desktop 内存上限**：Settings → Resources → Advanced → Memory，按物理内存给 Docker 分配（16GB 机器设 ~8GB；8GB 机器设 ~5GB）。

---

## 一、当前电脑要带走的东西

| 文件/目录 | 位置 | 用途 |
|---|---|---|
| **FastGPT 部署目录** | `C:\Users\liuhaotian\fastgpt-deploy\`（含 `docker-compose.yml`） | 核心，整个拷走 |
| 知识库文档 | `项目\examples\dify_bot\knowledge\knowledge_base.md` | 建知识库用 |
| 框架项目 | 整个项目目录 | 测试用（不要拷 .venv） |

> compose 文件里已改好的配置（新电脑直接可用）：`x-fe-domain` = `http://127.0.0.1:3000`、
> sandbox proxy 地址、aiproxy token = `fastgpt_aiproxy_2026`、aiproxy 端口 `3007`。

---

## 二、新电脑部署步骤

### 1. 环境准备

```powershell
# Docker Desktop + WSL2（管理员）
wsl --install          # 装完重启
winget install Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
```

### 2. Ollama + embedding 模型（知识库向量化必需）

```powershell
# 装 Ollama（https://ollama.com/download），然后：
ollama pull bge-m3
# 对外监听（关键！否则容器访问不到）：
$env:OLLAMA_HOST = "0.0.0.0:11434"   # 或 Ollama 设置里配置，重启 Ollama
curl http://localhost:11434/api/tags  # 验证能看到 bge-m3
```

### 3. hosts 映射（关键！否则浏览器上传报 s3_upload_network_error）

管理员 PowerShell：

```powershell
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 fastgpt-minio"
ipconfig /flushdns
```

### 4. 部署 FastGPT

```powershell
# 把 fastgpt-deploy 目录拷到新电脑（或直接新建目录放 docker-compose.yml）
cd 你放的目录
docker compose up -d
```

- 镜像走阿里云国内源，首次拉取较久；
- 等 `docker compose ps` 里 **fastgpt-app 变成 Up**（首次初始化建索引，几分钟）；
- 访问 `http://127.0.0.1:3000`。

> 若 fastgpt-app 报 `Invalid environment variables`（FE_DOMAIN / AGENT_SANDBOX），检查 compose 开头锚点是否还在（本文件已填好）。

---

## 三、配置（浏览器操作，顺序固定）

### 1. FastGPT 登录
- `http://127.0.0.1:3000`，账号 **root**，密码 **1234**（登录后建议改）。

### 2. aiproxy 配模型渠道（`http://127.0.0.1:3007`，token `fastgpt_aiproxy_2026`）
| 渠道 | 类型 | Base URL | Key | 模型 |
|---|---|---|---|---|
| LLM | OpenAI 兼容 | `https://newapi.gosuncn.com/v1` | 公司网关 key | `deepseek-v4-flash` |
| Embedding | Ollama | `http://host.docker.internal:11434` | 占位（如 `ollama`） | `bge-m3` |

### 3. FastGPT 添加模型（设置 → 模型供应商）
- `deepseek-v4-flash`（LLM，从 OpenAI 兼容渠道）；
- `bge-m3`（**Embedding**，从 Ollama 渠道）——类型别选错，否则知识库索引下拉为空。

### 4. 建知识库
- 上传 `knowledge_base.md`，处理方式「高质量」，索引模型选 `bge-m3`。

### 5. 建 Agent（应用）
- 新建 Agent → 简单问答 → 关联知识库 → LLM 选 deepseek-v4-flash；
- 系统提示词（与 Dify 一致）：
  ```
  你是「XX商城」的客服助手，负责解答退换货、售后政策相关问题。
  要求：只根据知识库回答，知识库没有的如实说不知道，不编造；回答简洁先给结论。
  ```
- 发布 → 记录 **appId**（Agent URL 里 `appId=...`）和 **API key**（对外服务 → API 密钥）。

---

## 四、接入 llmtest 验证

```powershell
$env:FASTGPT_BASE_URL = "http://127.0.0.1:3000"
$env:FASTGPT_API_KEY  = "fastgpt-你的key"
$env:FASTGPT_APP_ID   = "24位AgentID"

python examples/kb_bots/probe_fastgpt.py "退货期限是几天？"
```

- answer 答出 7/15 天 = 链路通；
- sources 为空是**已知**（FastGPT 兼容接口不返回引用，幻觉检测那条会跳过）。

跑测试：

```powershell
pytest examples/kb_bots/ --app fastgpt --llm-mode real --llm-provider openai --llm-base-url https://newapi.gosuncn.com/v1 --llm-model gpt-5.6-sol --llm-api-key sk-裁判key
```

---

## 五、与 Dify 切换（一条命令 + 严格交替）

| 动作 | 命令 |
|---|---|
| 切到 FastGPT | `cd fastgpt-deploy; docker compose up -d`（停 Dify：`cd dify\docker; docker compose stop`） |
| 切到 Dify | `cd dify\docker; docker compose up -d`（停 FastGPT：`cd fastgpt-deploy; docker compose stop`） |

> **必须一次只跑一个平台**（内存）。同一套用例：`--app fastgpt` / `--app dify` 切换被测对象。

---

## 六、常见坑

| 症状 | 原因 | 解法 |
|---|---|---|
| 浏览器上传报 s3_upload_network_error | 浏览器解析不了 `fastgpt-minio` | 加 hosts 映射（见二.3） |
| 上传报 appId is empty | adapter/请求缺 `appId` 或 `model` 非空 | FastGPT v1 接口 `model=""` + `body.appId`（adapter 已处理） |
| 知识库索引下拉空 | bge-m3 没登记为 Embedding | 模型配置类型选 Embedding，且走 Ollama 渠道 |
| fastgpt-app 反复 MongoWaitQueueTimeout | 内存不足 | 停另一个平台 / 加大 Docker 内存 |
| 访问 localhost 超时、127.0.0.1 通 | 环境 IPv6 ::1 不通 | 统一用 `127.0.0.1` |
