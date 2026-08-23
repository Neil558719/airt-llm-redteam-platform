# CI 发布门禁说明

当前 GitHub Actions 分为四个 job：

- `offline`：运行 Airt 自身测试、迁移校验，不访问 Dify 或 Judge。
- `shared-quality`：进入 `LLM应用测试框架`，运行共享 YAML 驱动的质量回归。
- `live-chatflow-security`：当 `DIFY_AGENT_API_KEY` 和 `JUDGE_API_KEY` secrets 都存在时，运行统一 Chatflow 工具安全测试。
- `unified-gate`：检查统一结果记录，拦截失败/错误记录、质量通过率不足、延迟超限和受限工具调用。

必需的 GitHub Secrets：

```text
DIFY_AGENT_API_KEY
JUDGE_BASE_URL
JUDGE_API_KEY
JUDGE_MODEL
```

未配置 live secrets 时，Chatflow live job 会跳过；这不等于安全测试通过。发布分支若要求真实安全门禁，必须配置这些 secrets，并将 `live-chatflow-security` 设为 required check。
