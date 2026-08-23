# AI Quality-Security Bridge Design

> 状态：已按 2026-08-23 的架构决策收敛。Airt 仅保留 `airt_dify_text` 和 `airt_dify_chatflow`；LLM 框架中的另一套 Dify 与 FastGPT 应用不注册为 Airt 目标，继续使用各自的 pytest 入口。

## Problem

Airt currently runs authorized red-team security cases against its own Dify text and Chatflow targets. The sibling LLM application test framework evaluates two different customer-service applications (one Dify and one FastGPT) for functional quality, RAG grounding, structure, latency, and judge scores. They are not the same applications and must never share credentials or application state.

## Decision

Merge the test platform layers, not the applications. Keep Airt's two named targets and adapt every response into one neutral `EvaluationContext`. Keep the two execution styles: Airt CLI/YAML for security and release gates; pytest/SDK for the independent LLM-framework quality suites.

## Non-goals

No live API calls, no application migration, no key rotation, no Chatflow graph changes, and no removal of existing adapters.
