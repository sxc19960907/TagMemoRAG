# Readiness smoke command — Implementation Plan

- [x] Read backend specs and shared thinking guides.
- [x] Inspect existing CLI, MVP integration, QueryPlan, answer, and bundle tests.
- [x] Add a small readiness helper module with:
  - isolated workspace creation/cleanup
  - deterministic config/doc setup
  - build/retrieve/answer/queryplan/bundle checks
  - JSON-safe report dataclasses or dict builders
- [x] Wire `tagmemorag readiness smoke` in `cli.py`.
- [x] Add unit/CLI tests for:
  - success path
  - retained workdir
  - bounded failure result/non-zero exit
- [x] Document the command in README and production operations guide.
- [x] Run focused tests:
  - `uv run pytest tests/unit/test_cli.py tests/unit/test_mvp_integration_acceptance.py tests/unit/test_manual_bundle.py tests/unit/test_queryplan_api_wireup.py -q`
- [x] Run `git diff --check`.
- [ ] Commit, archive, and journal.

## Risk Notes

- API globals are process-global; tests and helper should reset answer/reranker/queryplan caches around smoke execution.
- Temporary workspace cleanup should preserve artifacts when `--keep-workdir` is set or when caller uses an explicit workdir.
- Failure output should be useful but sanitized.

## Results

- Added `src/tagmemorag/readiness.py` with the local smoke orchestration and JSON-safe report shape.
- Added `tagmemorag readiness smoke` with `--workdir` and `--keep-workdir`.
- The command validates build, retrieve+noop answer, QueryPlan persistence, and bundle round-trip in an isolated local workspace.
- Successful default runs clean up the temporary workspace; explicit or failed runs report and preserve a workspace for inspection.

## Verification

- `uv run python -m tagmemorag readiness smoke` -> passed.
- `uv run pytest tests/unit/test_cli.py -q` -> 17 passed.
- `uv run pytest tests/unit/test_cli.py tests/unit/test_mvp_integration_acceptance.py tests/unit/test_manual_bundle.py tests/unit/test_queryplan_api_wireup.py -q` -> 35 passed.
- `git diff --check` -> passed.
