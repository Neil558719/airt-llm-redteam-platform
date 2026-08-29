# CI 发布门禁说明

当前 GitHub Actions 分为四个 job：

- `offline`：运行 Airt 自身测试、迁移校验，不访问 Dify 或 Judge。
- `shared-quality`：进入 `LLM应用测试框架`，运行共享 YAML 驱动的质量回归。
- `live-chatflow-security`：在本机 Self-hosted Runner 上运行统一 Chatflow 工具安全测试。
- `unified-gate`：检查统一结果记录，拦截失败/错误记录、质量通过率不足、延迟超限和受限工具调用。

实时 Chatflow Job 使用 Runner 标签 `self-hosted, windows, dify-local`，因为 GitHub-hosted runner 无法访问本机 `localhost`。Runner 应安装在 Dify 所在机器或能访问 Dify 的内网机器上；该机器需要预先启动 Dify、Judge 和测试工具服务。

必需的 GitHub Secrets：

```text
DIFY_AGENT_API_KEY
JUDGE_BASE_URL
JUDGE_API_KEY
JUDGE_MODEL
```

Self-hosted Runner 直接读取仓库中的 `config.dify.agent.yaml`，因此其中的 `http://127.0.0.1/v1` 指向 Runner 本机的 Dify。若 Dify 在同一内网其他机器上，只需把该配置中的 `base_url` 改为内网地址。

仓库内的 `push` 会自动执行本机实时 Job；手动运行 workflow 时勾选 `run_live=true` 也会执行。普通 `pull_request` 默认只运行离线 Job，避免不受信任的外部 PR 使用本机 Runner；需要对受信任 PR 执行实时测试时，可手动触发 `run_live=true`，并将 `unified-gate` 设为 required check。

门禁 Job 会额外生成：

- `reports/ci/unified-gate.junit.xml`：供测试报告插件展示每条用例；
- `reports/ci/unified-gate.sarif`：供代码扫描或安全平台展示门禁违规；
- `airt-unified-gate` artifact：保存以上结果，便于审计和定位失败。

门禁脚本也支持在本地或 CI 中增加基线比较：

```powershell
.\.venv\Scripts\python.exe scripts\unified_gate.py `
  --results gate-results\security.jsonl `
  --results gate-results\quality.jsonl `
  --baseline baselines\chatflow-assess.jsonl `
  --min-answer-overlap 0.4 `
  --junit reports\ci\unified-gate.junit.xml `
  --sarif reports\ci\unified-gate.sarif
```

基线比较会拦截用例缺失、状态变化、回答相似度下降和工具调用集合变化；基线文件应由确认通过的测试运行显式保存，不应自动覆盖。
