# M12 Code Context

## Existing Search Flow

- `src/tagmemorag/api.py` owns `/search`.
- The response already includes `build_id`, `kb_name`, `trace_id`, `results`, `search_time_ms`, and `cache`.
- Cache hit responses are reconstructed from a cached body that excludes request-local fields. M12 should follow that pattern for any new `search_id`.
- `SearchRequest` already includes `kb_name`, search params, and optional `SearchFilters`.
- Tag governance currently resolves tag filters at the API boundary via `_governed_filter_dict()`.

## Existing Eval Flow

- `src/tagmemorag/eval/dataset.py` defines JSONL `EvalCase`, `ExpectedResult`, and thresholds.
- Existing matcher fields: `source_file`, `header`, `anchor_key`, `text_contains`, and `metadata`.
- `src/tagmemorag/eval/runner.py` builds or loads KBs and runs `wave_search()` directly.
- Reports truncate long result text to 500 chars.
- `tests/fixtures/eval/coffee.jsonl` currently has three cases.

## Existing API/Auth Patterns

- API routes use `Depends(require_scope(...))`, `rate_limit_dep`, and `ensure_kb_access(api_key, kb_name)`.
- Known service errors should use `ServiceError(ErrorCode.INVALID_INPUT/INVALID_REQUEST/...)`.
- Harder admin operations currently use `admin`; rebuild/library writes use `rebuild`.

## Existing Storage Patterns

- `manual_library.py` resolves roots with `Path(...).resolve()` and checks path containment.
- Persistent JSON writes use `storage.atomic.atomic_write()`.
- Runtime graph state remains separate from file-backed source-of-truth state.

## Existing UI Patterns

- `/admin/manual-library` is a Jinja2 shell plus vanilla JS/CSS.
- It stores a Bearer token in `sessionStorage`.
- Tables are dense, filterable, and operations-oriented.
- M12 can reuse this style but should consider a separate route to avoid crowding the manual library page.
