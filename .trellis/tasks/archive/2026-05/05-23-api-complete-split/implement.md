# Complete API Entrypoint Split Implementation Plan

1. [x] Create focused API modules and pass current API globals into focused
   modules.
2. [x] Extract search/retrieve/answer helpers to `api_search.py`; leave wrappers in
   `api.py` for compatibility.
3. [x] Extract feedback route execution to `api_feedback.py`.
4. [x] Extract manual/manual-library route execution to `api_manual_routes.py`.
5. [x] Extract admin cache/generation helpers to `api_admin.py`.
6. [x] Update `api.py` route bodies to delegate and trim unused imports.
7. [x] Update directory-structure spec.
8. [x] Run API-focused tests:
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
9. Commit, archive, record journal, and return to main RAG work.

## Rollback Points

- If dependency injection becomes noisy, keep an API-layer module function small
  and pass only the exact dependencies it needs.
- If a route group has broad coupling, preserve wrappers in `api.py` and extract
  only the execution helper beneath it.
- If tests rely on a private `api.py` helper, restore it as a wrapper rather than
  moving tests first.
