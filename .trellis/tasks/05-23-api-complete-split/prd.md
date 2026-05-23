# Complete API Entrypoint Split

## Goal

Finish the API slimming effort in one cohesive task so `src/tagmemorag/api.py`
is a thin FastAPI wiring module rather than the owner of every route's business
logic.

## Requirements

- Preserve all current HTTP paths, methods, auth dependencies, status codes,
  response shapes, middleware behavior, and error handling behavior.
- Keep compatibility for existing imports and mutable globals:
  `tagmemorag.api.app`, `settings`, `app_state`, `embedder`,
  `_retrieve_impl`, request models, and answer/reranker caches used by tests and
  readiness/provider smoke helpers.
- Move search/retrieve/answer execution logic out of `api.py` into focused
  API-layer service modules.
- Move feedback route execution logic out of `api.py`.
- Move manual-library route execution logic out of `api.py` as far as practical
  without changing decorators or auth wiring.
- Move admin generation/cache helpers out of `api.py`.
- Keep `api.py` responsible for app creation, route decorators, dependency
  declarations, and delegating to the focused modules.
- Avoid lower-layer imports of `tagmemorag.api`; new API-layer modules receive
  runtime dependencies explicitly or via a small API runtime facade.
- Leave unrelated untracked files untouched.
- Return to the main RAG robustness / answer-quality work after this task.

## Acceptance Criteria

- [x] `api.py` is meaningfully reduced beyond the prior 2211-line baseline.
- [x] Search/retrieve/answer helper logic lives outside `api.py`, while
  `_retrieve_impl` remains import-compatible from `tagmemorag.api`.
- [x] Feedback route execution lives outside `api.py`.
- [x] Manual-library route execution is moved out or delegated enough that
  `api.py` no longer owns the full manual-library workflow bodies.
- [x] Admin cache/generation execution lives outside `api.py`.
- [x] API-focused tests pass.
- [x] Directory-structure spec records the final API module boundaries.
