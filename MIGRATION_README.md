# airt 平台迁移包

本包是当前工作区的可迁移快照，包含原有纯文本 Chat 测试和新增 Agent/Chatflow 工具调用测试。目标是让另一台 Windows 电脑在 Python 3.14 上重新安装并验证，不覆盖原有功能。

## 包含内容

- `src/airt/`：CLI、OpenAI-compatible/Dify 适配器、Judge、报告和归档模块。
- `tests/`：离线回归测试，包括 Agent profile、SSE、工具调用和报告归档测试。
- `cases/`：通用、纯文本 Dify、Agent/Chatflow 三类用例。
- `config.dify.yaml`：原有纯文本 `target`，并包含可选的独立 `agent` profile。
- `config.dify.agent.yaml`：独立 Chatflow profile 示例。
- `dify_agent_tools/`：无害工具 OpenAPI、固定 canary 回显服务、Chatflow 重建参考脚本。
- `knowledge/`、`prompts/`、`docs/`：测试知识库、系统提示词副本和文档。

包内不包含 `.git`、`.claude`、虚拟环境、缓存、旧 `runs/`/`reports/`、数据库备份、`.env` 或任何 API Key。

## Python 3.14 结论

当前开发机是 Python 3.10，不能替目标机完成 Python 3.14 实机验收。已对固定运行依赖进行 CPython 3.14/Windows wheel 可用性预检，核心依赖具备安装条件；但最终是否可运行必须由目标机执行下面的验收命令确认。

运行依赖和测试依赖分开：生产运行只需 `pip install -e .`；需要离线回归时再安装 `pip install -e ".[test]"`。如果目标机的 pip 对测试依赖报告冲突，先升级 pip，再记录具体错误，不要把生产依赖替换成未验证版本。

## 目标机安装

在解压后的包根目录执行 PowerShell：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe verify_migration.py
.\.venv\Scripts\airt.exe --help
```

开发回归环境额外执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

## 两种模式

原有纯文本 Chat 不变：

```powershell
$env:DIFY_API_KEY = "目标环境重新生成的纯文本应用 Key"
$env:JUDGE_API_KEY = "独立裁判模型的 Key"
.\.venv\Scripts\airt.exe run --config config.dify.yaml --cases cases/dify.yaml --out runs/migration-text
```

新增 Agent/Chatflow 显式切换：

```powershell
$env:DIFY_AGENT_API_KEY = "目标环境重新生成的独立 Chatflow Key"
.\.venv\Scripts\airt.exe run --config config.dify.yaml --target-profile agent --cases cases/dify-agent.yaml --out runs/migration-agent
```

Agent profile 只在显式选择时读取 `DIFY_AGENT_API_KEY`。两个模式必须使用独立 Dify 应用、Key、用例集和输出目录。

纯文本配置默认启用独立 Judge，因此必须同时设置 `JUDGE_API_KEY`。任何 Key 都不要写入 YAML、代码、报告或 Git。

## Dify 迁移顺序

1. 在源 Dify 做数据库备份，并记录 Dify 版本、应用模式、知识库文件、系统提示词和 Chatflow 图版本。
2. 在目标 Dify 先重建隔离纯文本测试应用和虚构测试知识库，不修改生产应用。
3. 复制 `prompts/dify/订单客服系统提示词.md` 正文到实际生效的系统提示词/LLM 节点。
4. 为目标纯文本应用重新生成 API Key，注入 `DIFY_API_KEY`。
5. 创建独立 Agent/Chatflow 应用，工作流保持：`start -> 工具授权路由 -> query_order/拒绝回复`。
6. 导入 `dify_agent_tools/custom_tool_openapi.yaml`，只允许访问固定 canary 回显服务。
7. 启动 `python dify_agent_tools/echo_server.py 18080`。Docker Dify 通常使用 `host.docker.internal:18080`，原生部署按目标网络拓扑调整。
8. Docker SSRF 代理只允许测试回显服务的精确主机名，不开放整个私有网段。
9. 为目标 Chatflow 重新生成 API Key，注入 `DIFY_AGENT_API_KEY`。
10. 先验证纯文本，再验证 Agent；确认 `query_order` 可观测、`send_notice` 未被诱导调用。

`provision_agent_app.sql` 和 `migrate_agent_to_chatflow.sql` 是特定 Dify 版本的重建参考，不是跨版本通用导入格式。执行 SQL 前必须备份数据库、核对表结构和租户，优先使用 Dify 官方导出/导入能力。

## 回滚

迁移失败时保留失败运行目录和报告归档，删除新建的测试应用、知识库、工具和 Key，或恢复迁移前数据库备份。不要回滚、覆盖或修改原有纯文本应用和生产资源。

## 安全边界

只测试自有或获得明确授权的应用。所有订单、工具地址和 canary 都是虚构测试数据；不要把真实订单、客户信息、密码、Token、支付、通知或外联工具接入测试 Chatflow。
