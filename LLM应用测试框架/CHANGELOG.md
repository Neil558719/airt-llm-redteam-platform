# CHANGELOG · 开发记录

> 记录本项目开发过程中**所有较大的改动**与**遇到的问题及解决**，便于复盘与迁移后还原上下文。

---

## 阶段一 · 框架核心（初始构建）

**改动**
- 建立 `llmtest` 包：Config（env/pytest 参数统一）、LLMClient 抽象层（Mock / OpenAI 兼容 / Anthropic）。
- 四类基础断言：语义（`assert_semantic_match`）、相似度（`assert_similarity`）、JSON Schema（`assert_valid_json` / `assert_json_schema`）、LLM-as-Judge（`assert_llm_judge`）。
- 幻觉检测模块：`assert_hallucination_rate`（拆事实断言 → 逐条核对 → 幻觉率）。
- 自包含 HTML 报告 + SVG 图表看板（通过率 / 准确率 / 幻觉率 / 延迟）。
- pytest 插件（`pytest11` entry point）+ fixtures（`app_under_test` / `llm_client` / `record_metric`）。

**遇到的问题与解决**
- `_timed` 计时器初版实现为嵌套类导致 TypeError → 改为 `@contextmanager`。
- Mock 语义对长回答余弦被稀释（0.485 < 0.7）→ 加"期望包含度"取 `max(cosine, containment)`。

## 阶段二 · 被测对象 vs 裁判 分离

**改动**
- `register_app` / `AppRegistry` / `--app` 切换被测对象；`--app-model` 支持裸模型当被测。
- 适配器模式：`ask(question) -> AppResponse(answer, sources)`，`track_latency()` 自动计时。
- 被测来源优先级：`--app` > `--app-model` > 注册默认 > Mock。

**遇到的问题与解决**
- 用户 PowerShell 设了环境变量但测试仍走 Mock → 会话作用域问题，报告头部加"被测对象 / 裁判"环境行辅助诊断。

## 阶段三 · 终端切换 + 真实模型接入

**改动**
- `--app-*` / `--llm-*` 参数 + `LLM_APP_*` / `LLM_*` 环境变量，命令切换被测与裁判。
- provider 别名（deepseek/qwen/zhipu/moonshot/ollama/local），自动补默认 base_url。
- 瞬时错误重试（5xx/429/超时）`_retry_call`。
- 真实网关跑通：被测 deepseek-v4-flash + 裁判 gpt-5.6-sol（公司网关 newapi）。

**遇到的问题与解决**
- 网关 502 → 加重试；报告区分"断言未通过"vs"异常/错误"。
- Judge 只给 1 分 → `assert_llm_judge` 需传 `question`（裁判要看原题）。
- 真实模型语义/Judge 判定比 Mock 严格 → 期望口径对齐知识库（如"普通 7 天 / 质量 15 天"分开）。

## 阶段四 · 报告与测试工程化

**改动**
- 历史报告归档：时间戳副本 + `reports/index.html`。
- `tests/` 重组为双模式（Mock + 真实模型通用），10 条用例。
- 报告增加「历史运行对比」表 + `history.json`。
- 图表标题 / 条形标签字号调整。

**遇到的问题与解决**
- 用户环境无 embedding → `assert_similarity` 框架级自动 `pytest.skip`（`embedding_available()` 探测 + `EmbeddingUnavailableError`）。
- 打分制 5 → 100（scale、min_score、预设 rubric、所有用例/文档同步）。

## 阶段五 · Dify 接入

**改动**
- `examples/dify_bot/`：Dify 适配器（chat-messages 接口，retriever_resources → sources）、探针、10 条用例、question_bank。
- 知识库文档 `knowledge_base.md`（分段友好：标题+连贯段落，避免列表碎片）。
- 批量回归、双裁判对比、历史对比、拒答/换述/多轮/相关性维度。

**遇到的问题与解决**
- Dify 本地 Docker 部署：GitHub 网络（codeload zip）、daocloud 加速器、db_postgres 慢启动被 skip（重跑恢复）。
- 知识库"答不上"：检索命中碎片（标题单成块）→ 重写为分段友好结构。
- Dify 系统提示词 + key 分工：被测 key 在平台内，pytest 只要裁判 key。

## 阶段六 · FastGPT 接入（第二次踩坑最多）

**改动**
- `examples/kb_bots/`：**多平台共享套件**（一套用例 `--app dify` / `--app fastgpt` 切换）。
- FastGPT 适配器（OpenAI 兼容接口 + appId + chatId 多轮 + sources 多路径容错）。

**遇到的问题与解决**
- FastGPT 全家桶（13 容器）**内存要求高** → 12GB 机器两个平台不能同跑，严格交替。
- 部署系列：FE_DOMAIN / AGENT_SANDBOX env 校验空 → 补值；mongo 连接池超时 → 等初始化 + 重启。
- aiproxy 模型：bge-m3 被当 chat（404 / does not support chat）→ 走 Ollama 渠道 + 标 Embedding 类型。
- FastGPT OpenAI 兼容接口 `appId is empty` → 源码定位：`model=""` + `body.appId`。
- FastGPT 上传 s3_upload_network_error → hosts 映射 `fastgpt-minio`。
- 内存崩溃（`0xc0000005`）→ Docker 强制删容器释放；切换前必须停另一个平台。
- Dify nginx 长时间运行后 80 端口失效 → 重启 nginx + api。

## 阶段七 · 工程化扩展

**改动**
- **数据驱动问题集**：问题从 `examples/kb_bots/data/knowledge_questions.json` 读（改问题不动代码）。
- **CI 脚本**：`scripts/ci_run.py` 一条命令两档（`--smoke` Mock 冒烟 / `--regression` 真实回归 / `--all`）。
- **超时 + 重试**：`[ci]` extras（pytest-timeout / pytest-rerunfailures），回归自动 `--timeout=900 --reruns=1`。
- **项目整理**：清理缓存 / 过期报告归档；`probe_embedding.py` 移到 `scripts/`。

## 待办 / 可选方向

- RAG 检索质量单独评估（区分"检索没召回"vs"生成不忠实"）。
- 多维质量雷达图（相关性/忠实度/有用性/准确性各维度）。
- 失败自动归因（模型 / 检索 / 提示词）。
