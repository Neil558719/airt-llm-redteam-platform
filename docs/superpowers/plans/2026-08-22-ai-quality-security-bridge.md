# AI Quality-Security Platform Bridge Implementation Plan

> 收敛说明（2026-08-23）：原计划中的“四目标 Airt 注册”已取消。Airt 目标注册表只保留 `airt_dify_text` 和 `airt_dify_chatflow`；`dify_quality` 与 `fastgpt_quality` 仍属于独立的 LLM 应用测试框架，不做 Airt 原生兼容。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不混淆四个真实客服应用的前提下，把 Airt 的安全测试执行层与 LLM 应用测试框架的质量评测能力通过统一上下文和目标注册表连接起来。

**Architecture:** 保留现有 Airt CLI/YAML 和 LLM 框架 pytest/SDK 两种入口。新增 `EvaluationContext` 作为跨适配器的中立结果对象，新增带环境变量插值的目标注册表；现有 adapter 不删除、不改成共享密钥。桥接对 `llmtest` 使用可选导入，未安装时 Airt 仍可独立运行。

**Tech Stack:** Python 3.10+, Pydantic 2, PyYAML, pytest, dataclasses, optional local `llmtest` package.

**Spec:** `docs/superpowers/specs/2026-08-22-ai-quality-security-bridge-design.md`

## Global Constraints

- 四个目标必须使用独立的环境变量和 API Key：`dify_quality`、`fastgpt_quality`、`airt_dify_text`、`airt_dify_chatflow`。
- 不修改真实 Dify/FastGPT 应用、知识库、Prompt 或会话状态。
- 旧 Airt 入口和 `LLM应用测试框架` 入口保持兼容。
- 不在日志、报告或测试输出中打印 API Key。

---

### Task 1: Add the bridge design and failing tests

**Files:**
- Create: `docs/superpowers/specs/2026-08-22-ai-quality-security-bridge-design.md`
- Create: `tests/test_evaluation_bridge.py`
- Create: `tests/test_target_registry.py`

**Interfaces:**
- `EvaluationContext.from_reply(reply, conversation_id=None, latency_ms=None)`
- `EvaluationContext.to_app_response()`
- `load_target_registry(path)`
- `TargetRegistry.resolve(name)`

- [ ] **Step 1: Write tests** for Reply conversion, AppResponse conversion, missing optional llmtest import, environment interpolation, four-target resolution, and missing target errors.
- [ ] **Step 2: Run tests to verify they fail** with missing-module or missing-symbol errors.

### Task 2: Implement the neutral evaluation context

**Files:**
- Create: `src/airt/evaluation_bridge.py`
- Modify: `src/airt/__init__.py`
- Test: `tests/test_evaluation_bridge.py`

**Interfaces:**
- `EvaluationContext` dataclass fields: `answer`, `sources`, `tool_calls`, `conversation_id`, `latency_ms`, `usage`, `raw`.
- `from_reply` preserves Airt tool-call observations and maps answer text/sources.
- `to_app_response` returns `llmtest.specs.AppResponse` when importable, otherwise a structurally compatible fallback object.

- [ ] **Step 1: Implement the dataclass and conversion helpers.**
- [ ] **Step 2: Run bridge tests and verify they pass.**

### Task 3: Implement target registry and example configuration

**Files:**
- Create: `src/airt/target_registry.py`
- Create: `targets.example.yaml`
- Test: `tests/test_target_registry.py`

**Interfaces:**
- `RegisteredTarget` validates provider (`dify`, `fastgpt`, `openai_compatible`), app type (`chat`, `advanced-chat`), URL, key, and optional model/app ID.
- `TargetRegistry.targets` maps names to `RegisteredTarget`.
- `TargetRegistry.resolve(name)` raises a clear error listing available names.
- `load_target_registry(path)` expands `${VAR}` and `${VAR:-default}` without exposing values.

- [ ] **Step 1: Implement Pydantic models and YAML loader.**
- [ ] **Step 2: Add four isolated target examples with distinct variable names.**
- [ ] **Step 3: Run registry tests and verify they pass.**

### Task 4: Add offline integration coverage and documentation

**Files:**
- Create: `tests/test_bridge_matrix.py`
- Modify: `README.md`
- Create: `docs/统一目标注册与质量安全桥接说明.md`

**Interfaces:**
- Matrix test creates representative replies for Dify text, Dify Chatflow, LLM-framework Dify, and FastGPT and converts each to `EvaluationContext`.
- Documentation explains which target owns which key and which suite is reusable vs provider-specific.

- [ ] **Step 1: Add matrix tests with no network calls.**
- [ ] **Step 2: Document PowerShell setup using separate environment variables.**
- [ ] **Step 3: Run the complete Airt test suite and bridge tests.**

### Task 5: Final verification

**Files:**
- No production file changes.

- [ ] **Step 1: Run `pytest -q` from the project root.**
- [ ] **Step 2: Run `python verify_migration.py`.**
- [ ] **Step 3: Inspect the diff and backup manifest; report exact results and remaining phase-2 work.**
