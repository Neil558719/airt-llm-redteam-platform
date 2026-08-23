# Dify 迁移验收清单

## 源环境备份

- [ ] 已确认获得目标应用的授权测试许可
- [ ] 已备份 Dify 数据库
- [ ] 已记录 Dify 版本和部署方式
- [ ] 已记录纯文本应用配置、知识库文件和系统提示词版本
- [ ] 已记录独立 Chatflow 的工作流图、工具定义和发布版本
- [ ] 未把 API Key、数据库密码或生产数据写入迁移包

## 目标环境重建

- [ ] 原有纯文本 Chat 作为独立测试应用重建
- [ ] 测试知识库重新上传 `knowledge/dify/` 三个虚构 Markdown
- [ ] 系统提示词与 `config.dify.yaml` 的 `target.system_prompt` 保持一致
- [ ] 独立 Agent/Chatflow 已创建，没有覆盖纯文本 Chat
- [ ] 工作流包含工具授权路由、`query_order` 和拒绝分支
- [ ] 工作流变量字段按目标 Dify 版本要求配置
- [ ] `custom_tool_openapi.yaml` 已导入隔离测试应用
- [ ] `echo_server.py` 仅监听测试端口并返回固定 canary
- [ ] Docker 场景只对白名单加入测试回显主机名

## 凭据

- [ ] 目标环境重新生成 `DIFY_API_KEY`
- [ ] 目标环境重新生成 `DIFY_AGENT_API_KEY`
- [ ] Judge 使用独立的 `JUDGE_API_KEY`
- [ ] 凭据仅通过环境变量或密钥管理器注入
- [ ] 报告、日志、YAML 和 Git 中没有凭据

## Python 3.14 离线验收

- [ ] `py -3.14 -m venv .venv`
- [ ] `pip install -e .`
- [ ] `pip check`
- [ ] `python verify_migration.py`
- [ ] `airt --help`
- [ ] `airt list --cases cases`
- [ ] `airt list --cases cases/dify-agent.yaml`
- [ ] `pip install -e ".[test]"`
- [ ] `python -m pytest -q`

## Dify 实网验收

- [ ] 纯文本 blocking 测试成功，使用独立 `runs/migration-text`
- [ ] Agent streaming 收到 `message_end` 或 `workflow_finished`
- [ ] 正常用例观测到 `query_order`
- [ ] `send_notice` 在禁止用例中未被调用
- [ ] 报告显示 Agent/工具调用模式和脱敏后的 ToolCall
- [ ] `reports/archive/` 生成不可覆盖归档
- [ ] 迁移失败时可删除新资源或恢复数据库备份
