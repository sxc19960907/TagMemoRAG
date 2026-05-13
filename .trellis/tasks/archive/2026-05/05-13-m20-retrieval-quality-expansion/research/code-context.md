# M20 Code Context

## Existing Eval Surface

- `src/tagmemorag/eval/dataset.py` loads JSONL eval suites into `EvalCase` and `ExpectedResult`.
- Expected matchers already support `source_file`, `header`, `anchor_key`, `text_contains`, and `metadata`.
- Cases already support `kb_name`, free-form `tags`, `notes`, `top_k_override`, and per-case threshold fields.
- `src/tagmemorag/eval/runner.py` builds or loads KBs, embeds each query, runs ranking, matches expectations, computes metrics, and returns `EvalReport`.
- `src/tagmemorag/eval/report.py` serializes summary, cases, expected matchers, actual top-k, and config snapshot.
- CLI command `tagmemorag eval run` already supports `--suite`, `--docs`, `--config`, `--output`, `--top-k`, `--kb`, `--reuse-built-kb`, `--eval-data-dir`, and threshold flags.

## Current Fixtures and Tests

- Current fixture suite is `tests/fixtures/eval/coffee.jsonl`.
- Current manual fixture is `tests/fixtures/coffee_machine.md`.
- `tests/e2e/test_eval_cli.py` verifies the coffee suite passes and threshold failures are reported.
- Unit tests cover dataset validation, matcher behavior, metrics aggregation, and isolated eval storage.

## Important Gap for M20

- `run_eval()` currently calls `wave_search()` directly.
- API/CLI search call `execute_search()`, which now handles exact local search, Qdrant ANN preselection, ANN fallback, and execution diagnostics.
- To evaluate ANN behavior realistically, M20 should move `run_eval()` onto `execute_search()` or a shared equivalent search execution helper.

## Useful Existing Patterns

- `tests.unit.test_storage_state.FakeQdrantClient` is used by API/CLI/manual-library tests to cover Qdrant behavior without network access.
- Existing manual-library tests cover incremental rebuild, dirty state, Qdrant sync, and update paths.
- Existing ANN API/CLI tests show how to monkeypatch `QdrantVectorStore._create_client`.

## Candidate Files for Implementation

- `src/tagmemorag/eval/runner.py`
- `src/tagmemorag/eval/report.py`
- `src/tagmemorag/eval/dataset.py` if filters or scenario metadata are needed
- `tests/fixtures/product_manuals/**`
- `tests/fixtures/eval/product_manuals.jsonl`
- `tests/unit/test_eval_runner.py`
- `tests/e2e/test_eval_cli.py`
- `tests/unit/test_manual_library.py` or a new focused test file for incremental rebuild plus eval
- `README.md`
