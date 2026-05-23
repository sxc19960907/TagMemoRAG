# Slim API Entrypoint Implementation Plan

1. [x] Move API Pydantic request models into `api_models.py` and re-export them
   from `api.py`.
2. [x] Move QA-only helper functions into `api_qa.py`.
3. [x] Move manual-library form parsing, rebuild request helper, diagnostics helper,
   and audit sanitization into `api_manual.py`.
4. [x] Update imports and route call sites in `api.py`.
5. [x] Update directory structure spec with the new API module boundaries.
6. [x] Run focused API tests:
   - `tests/unit/test_api.py`
   - `tests/unit/test_answer_api.py`
   - `tests/unit/test_m2_api.py`
   - `tests/unit/test_m4_api_observability.py`
   - `tests/unit/test_api_trace.py`
   - `tests/unit/test_queryplan_api_wireup.py`
   - `tests/unit/test_queryplan_feedback_plan_id.py`
   - `tests/unit/test_retrieval_feedback_api.py`
   - `tests/unit/test_manual_bulk_import_api.py`
   - `tests/unit/test_manual_library_api.py`
   - `tests/unit/test_tag_suggestions_api.py`
   - `tests/unit/test_admin_indexgen_api.py`
   - `tests/unit/test_shutdown.py`
7. Commit, archive the task, record journal, and return to the main RAG work.

## Rollback Points

- If model extraction breaks import compatibility, re-export aliases from
  `api.py` before making deeper changes.
- If manual helper extraction introduces global-state confusion, keep the route
  body in `api.py` and only extract pure parsing/diagnostic helpers.
- If API-focused tests reveal broad router-coupling issues, stop after model and
  pure-helper extraction rather than forcing router modules in this task.
