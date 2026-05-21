# C6 Surface and Provider Verify — Execution Plan

## 0. Operating Rules

- Keep agentic default-off.
- Do not add live-network unit tests.
- Do not write provider secrets to config, logs, reports, task docs, or tests.
- Keep classic request behavior compatible when new fields are omitted.

## 1. Implementation Steps

### Step 1 — Config Contracts

- Add `AgenticConfig` and `AgenticDecisionConfig`.
- Add unit tests for defaults, YAML, and env overrides.

Validation:

```bash
uv run pytest tests/unit/test_config_env.py -q
```

### Step 2 — Request Surface and Mode Helper

- Add request fields and a pure mode resolver/stamper.
- Add API/request-model tests that default payloads still parse and overrides
  stamp safe strategy metadata.

Validation:

```bash
uv run pytest tests/unit/test_answer_api.py tests/unit/test_queryplan_plan.py -q
```

### Step 3 — Eval and Replay Force Mode

- Add `force_mode` to eval runner and CLI.
- Add `--force-mode` to replay CLI and report payload.
- Cover output snapshots in unit/CLI tests.

Validation:

```bash
uv run pytest tests/unit/test_eval_runner.py tests/e2e/test_eval_cli.py tests/unit/test_replay_cli.py tests/unit/test_replay_runner.py -q
```

### Step 4 — Provider Verify Decision Check

- Include decision env requirements when the decision provider is active.
- Add deterministic `decision` check when agentic or decision config is active.
- Update JSON/Markdown report tests.

Validation:

```bash
uv run pytest tests/unit/test_production_provider_verify.py tests/unit/test_cli.py -q
```

### Step 5 — Regression Gate

Run:

```bash
uv run pytest tests/unit/test_config_env.py \
  tests/unit/test_answer_api.py \
  tests/unit/test_eval_runner.py \
  tests/e2e/test_eval_cli.py \
  tests/unit/test_replay_cli.py \
  tests/unit/test_replay_runner.py \
  tests/unit/test_production_provider_verify.py \
  tests/unit/test_cli.py -q

uv run pytest -q

git diff --check
```

## 2. Exit Criteria

- [x] AC6.1-AC6.8 are all satisfied.
- [x] Full pytest passes.
- [x] C6 docs updated with validation results.
- [ ] C6 archived and committed.

## 3. Validation Results

- `uv run pytest tests/unit/test_answer_config.py tests/unit/test_config_env.py tests/unit/test_agentic_surface.py tests/unit/test_queryplan_request_budget.py tests/unit/test_answer_api.py -q`
  passed: 66 passed in 0.56s.
- `uv run pytest tests/unit/test_eval_runner.py tests/unit/test_cli.py tests/unit/test_replay_cli.py -q`
  passed: 35 passed in 9.14s.
- `uv run pytest tests/unit/test_answer_config.py tests/unit/test_config_env.py tests/unit/test_agentic_surface.py tests/unit/test_queryplan_request_budget.py tests/unit/test_answer_api.py tests/unit/test_eval_runner.py tests/unit/test_cli.py tests/unit/test_replay_cli.py tests/unit/test_replay_runner.py tests/unit/test_production_provider_verify.py -q`
  passed: 115 passed in 9.31s.
- `uv run pytest tests/e2e/test_eval_cli.py -q` passed: 3 passed in 2.02s.
- `uv run pytest -q` passed: 1019 passed, 2 skipped in 18.68s.
- `git diff --check` passed.
- `git diff --name-only HEAD -- src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py src/tagmemorag/retrieval.py src/tagmemorag/search_runtime.py`
  returned no files.
