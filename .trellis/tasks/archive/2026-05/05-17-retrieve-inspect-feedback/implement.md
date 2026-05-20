# Implementation Plan — Retrieve Inspect and Feedback

## Direction Gate 0

- [x] Confirm no ranking changes.
- [x] Confirm no visual evidence, assets, OCR, parent expansion, or `/answer`.

## Stage 1: Retrieve Inspect

- [x] Add `retrieve_inspect_payload()` to retrieval response builder module.
- [x] Attach `debug.retrieve_inspect` in `/retrieve` only when debug is enabled.
- [x] Add tests for safe shape.

## Stage 2: Feedback Extension

- [x] Extend feedback dataclass and parser with retrieve fields.
- [x] Add `/retrieve/feedback` submit route.
- [x] Add tests for persistence and auth.

## Stage 3: Validation

- [x] Run focused tests.
- [x] Run full tests.
- [x] Run eval CI.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_retrieval_feedback.py tests/unit/test_retrieval_feedback_api.py tests/unit/test_api.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```

Validation completed:

- `.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_retrieval_feedback.py tests/unit/test_retrieval_feedback_api.py tests/unit/test_api.py -q`
- `.venv/bin/python -m pytest tests/ -q`
- `.venv/bin/python scripts/run_eval_ci.py`
