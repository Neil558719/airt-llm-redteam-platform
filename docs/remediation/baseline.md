# P00 / B01：离线测试基线

记录日期：2026-10-20。源提交：`ae7675ed2420d2fd1695ce669fd508b7c304a538`。
任务：[B01 / Issue #7](https://github.com/Neil558719/airt-llm-redteam-platform/issues/7)。

## 环境与命令

Windows、Python 3.14.0、uv 0.12.9、pytest 9.1.1。工作区的 `work/env-b/root`
仅可编辑安装根项目 `.[test]`；`work/env-b/embedded` 仅可编辑安装内嵌项目 `.`。
根环境自动插件为 anyio/asyncio，无 llmtest；内嵌环境插件为 llmtest，无 airt 安装。
环境互相隔离，未借助插件禁用参数改变被测行为。

以下 `python` 指对应隔离环境的解释器，工作目录分别为仓库根或 `LLM应用测试框架/`。

| 阶段 | 目录与命令 | 实际结果 | 退出码 |
| --- | --- | --- | --- |
| 旧行为 | 根：`python -m pytest -q -ra -o addopts=''` | 235 passed, 1 skipped | 0 |
| 旧行为 | 内嵌：`python -m pytest -q -ra` | 14 passed, 2 failed | 1 |
| 旧收集 | 内嵌：`python -m pytest --collect-only -q` | 16 collected | 0 |
| 扩充后 RED | 内嵌：`python -m pytest -q -ra tests/test_rag_assistant.py` | 3 passed, 4 failed | 1 |
| 最终 GREEN | 根：同上，另加本地 `--junitxml` 路径 | 235 passed, 1 skipped | 0 |
| 最终 GREEN | 内嵌：`python -m pytest -q -ra`，另加本地 `--junitxml` 路径 | 20 passed | 0 |
| 最终收集 | 根 / 内嵌：`python -m pytest --collect-only -q` | 236 / 20 collected | 0 |
| 迁移兼容 | 根：`python verify_migration.py` | Migration verification passed | 0 |

根 `addopts` 自带 `-q`；显式清空它仅避免双重 quiet 隐藏实际数量，不改变收集范围。
唯一 skip 为根 `tests/test_live.py:17`：未提供明确 live 配置。内嵌没有 skip/deselect。

## 失败归因与执行范围

旧失败均在 `tests/test_rag_assistant.py`：两个忠实度正例用 7 天、买家付运费的旧资料，
核对 14 天、特殊商品例外、运费未明确的当前 Mock 答案，幻觉率均为 100%。
共享 YAML 已是当前业务版本。本次修复独立参考资料，不把 Mock 回答当作事实来源；
原有 0.4 / 0.3 阈值、检测器算法及原测试全部保留。

根配置 `testpaths = ["tests"]` 收集 236 个节点，不会进入内嵌测试目录。
旧 `shared-quality` 仅选择三个文件，实际只收集 6 个节点；修复后在内嵌工作目录
默认收集全部 5 个测试模块、20 个节点。根绿灯不能证明这 20 个节点已经执行。

## 证据与状态

完整日志保存在工作区 `work/b01-evidence/`，不提交日志、环境、HTML 或真实业务响应：
`root-baseline-summary.log`、`embedded-baseline-red.log`、`embedded-collect-baseline.log`、
`rag-expanded-red.log`、`rag-targeted-green.log`、`root-green.log`、`embedded-green.log`、
`root-collect-green.log`、`embedded-collect-green.log`、`ci-contract-audit.log`、
`migration-green.log`、两个 `*-green.xml` 及两个 `*-env-isolation.log`。

本地验证完成。GitHub CI、真实 Dify/Judge 验收、合并、Release 未在本任务执行。
没有启动或修改 Docker / Dify 服务；没有更改 live 门禁、产物协议或根套件默认范围。

边界：数字正反例仅验证最小数字事实。实测近似完整回答把 14 天改为 7 天时，
Mock token 裁判仍给出 0.0 幻觉率；本次未修改裁判算法。
此限制关联 B06 / A02，不能据本次绿灯声称全文事实检测可靠。
