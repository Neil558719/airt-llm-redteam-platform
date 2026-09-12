# Local Doctor And Preflight Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with test-first development and verify the full offline suite before claiming completion.

**Goal:** Make local Airt runs fail early with actionable diagnostics for configuration, case assets, credentials, and optional endpoint reachability.

**Architecture:** Keep the existing Typer CLI as the public interface and move pure diagnostic logic into a small `airt.doctor` module. The default doctor command remains offline and never contacts Dify or Judge; an explicit `--check-network` opt-in performs lightweight HTTP probes.

**Tech Stack:** Python 3.14, Typer, httpx, Pydantic, pytest.

**Spec:** The first local-hardening phase from the project roadmap: environment self-check and one-command preflight without changing GitHub Actions or test execution semantics.

## Global Constraints

- Never print API keys or Authorization headers.
- Default `airt doctor` must not send network requests.
- Existing `security`, `quality`, `release`, and `chatflow assess` behavior must remain compatible.
- Every new behavior must have a failing test before implementation.

### Task 1: Diagnostic engine

**Files:**
- Create: `src/airt/doctor.py`
- Test: `tests/test_doctor.py`

- [x] Write tests for missing credentials, valid configuration, and HTTP probe classification.
- [x] Run the focused tests and observe the expected failures.
- [x] Implement pure checks and a redacted diagnostic result model.
- [x] Run the focused tests again.

### Task 2: CLI integration

**Files:**
- Modify: `src/airt/cli.py`
- Test: `tests/test_cli.py`

- [x] Add `--cases`, `--target-profile`, and `--check-network` options while preserving defaults.
- [x] Validate case files through the existing case validator.
- [x] Render actionable Chinese diagnostics and return non-zero on failures.
- [x] Add CLI tests and run them.

### Task 3: User documentation and regression verification

**Files:**
- Modify: `README.md`
- Modify: `docs/统一运行手册.md`

- [x] Document the local preflight command and network opt-in behavior.
- [x] Run the complete offline test suite and inspect the final diff.
