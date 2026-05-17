# Implementation Plan — Retrieve Text Evidence API

## Direction Gate 0

- [x] Confirm this task reuses search ranking and does not alter `/search`.
- [x] Confirm text-only evidence; no assets/OCR/visual/LLM.

## Stage 1: Response Builder

- [x] Add `retrieval.py` with pure builders for evidence, citations, context pack, and answerability.
- [x] Add unit tests for builder shape and no-results behavior.

## Stage 2: API Route

- [x] Add `RetrieveRequest`.
- [x] Add `POST /retrieve`.
- [x] Reuse existing auth/rate-limit/KB access behavior.
- [x] Reuse existing search params and `execute_search`.

## Stage 3: Tests

- [x] Unit/API tests for success response.
- [x] Unit/API tests for no-result insufficient-evidence response.
- [x] Test context budget behavior.
- [x] Confirm `/search` compatibility tests still pass.

## Direction Gate 1

- [x] Verify response uses lineage IDs and request-scoped citation/context IDs correctly.
- [x] Verify no visual/answer-generation scope slipped in.

Gate notes:

- `/retrieve` reuses `execute_search` and does not change `/search`.
- Evidence/context IDs are request-scoped (`ev_*`, `cit_*`, `ctx_*`) and point to persistent `doc_id` / `chunk_id` when present.
- Scope remains text-only: no assets, OCR, visual evidence, image vectors, LLM, or `/answer`.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_api.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```
