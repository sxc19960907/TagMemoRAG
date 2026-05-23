# Complete API Entrypoint Split Design

## Target Shape

`api.py` remains the canonical module that exposes the FastAPI `app` and
compatibility globals. Route decorators stay in `api.py`; route bodies become
small delegators.

New API-layer modules:

- `api_runtime.py`: explicit runtime dependency container plus factory helpers
  that read current `api.py` globals at call time.
- `api_search.py`: search/retrieve/answer execution, cache keys, QueryPlan
  logging, reranker dispatch, and compatibility `_retrieve_impl`.
- `api_feedback.py`: feedback submit/list/review/promote route execution.
- `api_manual_routes.py`: manual and manual-library route execution using
  existing `api_manual.py` parsing/diagnostic helpers.
- `api_admin.py`: health/ready/metrics/cache/generation execution helpers.

Existing modules remain:

- `api_models.py`: request models.
- `api_qa.py`: QA route selection and clarification/not-ready payloads.
- `api_manual.py`: manual form parsing, rebuild helper, diagnostics helper.

## Compatibility

`api.py` re-exports the moved request models and exposes wrapper functions for
private helpers that external tests use, especially `_retrieve_impl`,
`_compute_cache_key`, and `_compute_search_id`.

The answer and reranker caches may move, but `api.py._ANSWER_GENERATOR_CACHE`
and `api.py._RERANK_DISPATCHER_CACHE` must remain aliases so readiness and
provider smoke helpers can clear them.

## Dependency Direction

New modules are still API-layer modules. They do not import `tagmemorag.api` at
module load. Instead `api.py` passes an `ApiRuntime` that contains the current
settings, app state, embedder, rebuild queue getter, and trace id helpers.

## Risk Controls

- Keep decorators and dependencies in `api.py` to avoid route registration churn.
- Move logic in chunks and run focused tests after each major group if needed.
- Preserve old helper function names in `api.py` as wrappers.
- Stop before splitting middleware/lifespan if route extraction already produces
  a thin enough entry point and tests are stable.
