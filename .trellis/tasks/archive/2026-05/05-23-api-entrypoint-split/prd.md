# Slim API Entrypoint

## Goal

Reduce the size and responsibility of `src/tagmemorag/api.py` without changing
public HTTP behavior, so the API entry point becomes easier to maintain before
returning to the main RAG robustness and answer-quality work.

## Requirements

- Preserve all current HTTP paths, methods, auth dependencies, response shapes,
  status codes, middleware behavior, and error handling behavior.
- Keep `tagmemorag.api.app`, `settings`, `app_state`, `embedder`, and existing
  public request model imports compatible with tests and integration callers.
- Move low-risk API-only request/response models out of `api.py` into a focused
  module while re-exporting them from `api.py` for compatibility.
- Move route-local helper logic that does not need FastAPI decorators or global
  mutable API state into focused helper modules.
- Avoid introducing lower-layer imports of `tagmemorag.api`; dependency
  direction remains entry-point to service layers.
- Do not change retrieval, answer, rebuild, manual-library, feedback, auth,
  metrics, tracing, or cache semantics as part of this refactor.
- Leave unrelated untracked files untouched.
- After the split, return to the main RAG robustness / answer quality roadmap.

## Acceptance Criteria

- [x] `api.py` line count is meaningfully reduced from its current 2705-line
  baseline.
- [x] Pydantic API request models live outside `api.py` and remain importable
  from `tagmemorag.api` for compatibility.
- [x] QA helper logic and manual-library helper logic are moved out of `api.py`
  when they can be extracted without behavior changes.
- [x] API-focused tests pass, including search/retrieve/answer, manual-library,
  feedback, auth/observability, queryplan, and generation admin coverage.
- [x] Directory-structure spec records the new API module boundaries.
