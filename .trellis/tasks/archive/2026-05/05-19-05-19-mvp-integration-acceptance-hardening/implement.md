# Implementation Plan

- [x] Read active task artifacts and backend specs.
- [x] Inspect existing focused tests for T1-T9/T1.5 to avoid duplicate coverage.
- [x] Add MVP integration acceptance tests.
- [x] Fix small integration defects only if tests expose them.
- [x] Run focused suite:
  - `uv run pytest tests/unit/test_mvp_integration_acceptance.py -q`
  - `uv run pytest tests/unit/test_answer_api.py tests/unit/test_queryplan_api_wireup.py tests/unit/test_reranker_api_e2e.py tests/unit/test_retrieval.py tests/unit/test_connectors_integration.py tests/unit/test_manual_bundle.py tests/unit/test_indexgen_derivative_paths.py tests/unit/test_replay_runner.py -q`
- [x] Run `git diff --check`.
- [x] Update acceptance matrix / follow-up notes if findings appear.
- [ ] Commit, archive, and journal.

## Results

- Added `tests/unit/test_mvp_integration_acceptance.py` with default-off, connector/search/answer/queryplan, visual safety, OCR-search, and connector bundle round-trip coverage.
- No product code changes were required; the only implementation adjustment was aligning test expectations to the existing contract that QueryPlan logs retrieve-stage warnings, while answer provider warnings stay in the answer payload.

## Verification

- `uv run pytest tests/unit/test_mvp_integration_acceptance.py -q` -> 5 passed.
- `uv run pytest tests/unit/test_answer_api.py tests/unit/test_queryplan_api_wireup.py tests/unit/test_reranker_api_e2e.py tests/unit/test_retrieval.py tests/unit/test_connectors_integration.py tests/unit/test_manual_bundle.py tests/unit/test_indexgen_derivative_paths.py tests/unit/test_replay_runner.py -q` -> 42 passed.
- `uv run pytest tests/unit/test_mvp_integration_acceptance.py tests/unit/test_answer_api.py tests/unit/test_queryplan_api_wireup.py tests/unit/test_reranker_api_e2e.py tests/unit/test_retrieval.py tests/unit/test_connectors_integration.py tests/unit/test_manual_bundle.py tests/unit/test_indexgen_derivative_paths.py tests/unit/test_replay_runner.py -q` -> 47 passed.
- `git diff --check` -> passed.

## Follow-Up Notes

- This task confirms MVP composition under deterministic/local providers and conservative defaults.
- Deferred items remain intentionally out of scope: real OCR/visual/connectors/providers, production traffic split, HA, streaming answers, and signed/encrypted bundles.
