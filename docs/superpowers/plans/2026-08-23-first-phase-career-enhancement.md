# 第一阶段求职展示增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended; not available in this session) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前已合并的 LLM 安全/质量测试平台增强为可接入 CI、可校验测试资产、可对比历史趋势、可追踪单次运行并可快速展示结果的求职项目。

**Architecture:** 复用现有 `evaluation-result-v1` JSONL、HTML/JSON 报告、Typer CLI 和 GitHub Actions。新增轻量的用例校验、运行统计/趋势和静态 Dashboard 模块，不引入数据库或 Web 服务；所有新增产物保持离线可重建。

**Tech Stack:** Python 3.14、Typer、Pydantic、PyYAML、Jinja2、pytest、GitHub Actions、静态 HTML。

**Spec:** 当前用户需求与项目现有《统一运行手册》、`evaluation-result-v1` 契约。

## Global Constraints

- 不打印或写入真实 API Key、Authorization 请求头或敏感配置。
- 保留现有四类报告目录：`reports/assess`、`reports/security`、`reports/quality`、`reports/release`。
- 不改变当前 Chatflow 安全、质量、release、assess 命令的默认行为。
- 新能力必须支持离线测试，不依赖 Dify 或 Judge 才能运行单元测试。
- 每个新增生产函数必须有测试，先写失败测试再实现。

### Task 1: 测试用例 Schema 校验

**Files:**
- Create: `src/airt/case_validation.py`
- Modify: `src/airt/cli.py`
- Create: `tests/test_case_validation.py`
- Modify: `docs/统一运行手册.md`

**Deliverable:** `airt cases validate <path>`，校验 YAML 类型、必填字段、ID 唯一性、category/tag/quality/tool 配置，并输出中文汇总。

- [ ] 写覆盖成功、重复 ID、非法字段/类型和目录递归的失败测试。
- [ ] 运行新增测试确认先失败。
- [ ] 实现纯离线校验函数和 CLI 子命令。
- [ ] 运行新增测试及完整 pytest。

### Task 2: 运行 ID 与失败分类

**Files:**
- Modify: `src/airt/models.py`
- Modify: `src/airt/unified_results.py`
- Modify: `src/airt/runner.py`
- Modify: `src/airt/report/json_report.py`
- Create/modify: `tests/test_run_metadata.py`

**Deliverable:** 每次运行有稳定 `run_id`、开始/结束时间和失败分类；目标请求、Judge、工具和平台错误可以区分。

- [ ] 写 JSONL 兼容性和失败分类测试。
- [ ] 运行测试确认先失败。
- [ ] 以 UUID/UTC 时间组合生成 run_id，并向后兼容旧 JSONL。
- [ ] 在 JSON/HTML/终端摘要中展示分类和 run_id。
- [ ] 运行完整 pytest。

### Task 3: 历史趋势与对比报告

**Files:**
- Create: `src/airt/report/trends.py`
- Modify: `src/airt/cli.py`
- Create: `tests/test_trends.py`
- Modify: `docs/统一运行手册.md`

**Deliverable:** `airt report trend --reports reports/<mode>` 读取历史归档，生成 `trend.json` 和 `trend.html`，展示安全分、质量分、延迟和失败数变化。

- [ ] 写多次归档、缺失指标和空目录测试。
- [ ] 运行测试确认先失败。
- [ ] 实现历史归档扫描和指标聚合。
- [ ] 增加 CLI 命令和中文趋势页面。
- [ ] 运行完整 pytest。

### Task 4: 静态测试 Dashboard

**Files:**
- Create: `src/airt/report/dashboard.py`
- Modify: `src/airt/cli.py`
- Create: `tests/test_dashboard.py`
- Modify: `.github/workflows/airt-quality-security.yml`
- Modify: `docs/统一运行手册.md`

**Deliverable:** `airt report dashboard` 生成总览页，链接四类最新报告、历史趋势和发布门禁结果；CI 上传报告和 Dashboard 作为 artifacts。

- [ ] 写 dashboard 链接、缺失目录和 HTML 转义测试。
- [ ] 运行测试确认先失败。
- [ ] 实现静态 HTML 生成，不启动服务、不发送网络请求。
- [ ] 在 CI 中上传 `reports/` 和 `artifacts/`。
- [ ] 运行完整 pytest。

### Task 5: 架构图、结果示例和求职文档

**Files:**
- Create: `docs/架构与测试闭环.md`
- Create: `docs/examples/sample-dashboard.html`
- Modify: `README.md`
- Modify: `docs/统一运行手册.md`

**Deliverable:** 文档化目标适配器、共享用例、Judge、报告和 CI 门禁闭环，提供脱敏的结果示例和面试可引用的量化指标模板。

- [ ] 编写架构图和数据流说明。
- [ ] 添加脱敏样例，禁止真实密钥和生产数据。
- [ ] 更新 README 的快速演示和简历项目描述。
- [ ] 检查链接、命令和目录与当前实现一致。

### Task 6: 全量验证与清理

**Files:**
- Modify as needed from previous tasks.

- [ ] 执行 `python -m pytest -q`。
- [ ] 执行 `airt cases validate shared_cases/unified_chatflow.yaml`。
- [ ] 执行离线 trend/dashboard 生成命令。
- [ ] 检查报告不包含 API Key、Authorization 或缓存垃圾。
- [ ] 更新计划勾选状态并记录验证结果。

## 验证记录

- 2026-08-23：.\.venv\Scripts\python.exe -m pytest -q，120 passed, 1 skipped。
- 共享用例校验通过：1 个文件、8 条用例。
- 已离线生成 eports/quality/trend.html 和 eports/dashboard.html。
- GitHub Actions YAML 已通过 PyYAML 解析检查。
