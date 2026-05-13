# implement.md - M12 Retrieval Quality Feedback Loop and Eval Dataset Growth

## Implementation Checklist

- [ ] Read current backend specs with `trellis-before-dev` before coding.
- [ ] Add `retrieval_feedback.py` with feedback dataclasses, validation, serialization, and bounded text handling.
- [ ] Implement safe per-KB feedback paths under the storage root.
- [ ] Implement JSONL append for immutable feedback events.
- [ ] Implement review overlay read/write for feedback status and operator notes.
- [ ] Implement feedback listing with bounded filters: `kb_name`, status, outcome, limit, and optional query substring.
- [ ] Add `search_id` to `/search` responses and ensure cache hits recompute request-local linkage fields.
- [ ] Add API request/response models for feedback submit/list/review/promote preview/promote.
- [ ] Add feedback API endpoints:
  - [ ] `POST /search/feedback`
  - [ ] `GET /search/feedback`
  - [ ] `PATCH /search/feedback/{feedback_id}`
  - [ ] `POST /search/feedback/promote/preview`
  - [ ] `POST /search/feedback/promote`
- [ ] Enforce auth and KB allowlist access:
  - [ ] `search` scope for feedback submit
  - [ ] `admin` scope for list/review/promote in MVP
- [ ] Implement eval promotion preview from feedback records.
- [ ] Implement eval draft export with deterministic case IDs and explicit append/overwrite behavior.
- [ ] Add CLI `feedback` command group:
  - [ ] `submit`
  - [ ] `list`
  - [ ] `review`
  - [ ] `promote-preview`
  - [ ] `promote`
- [ ] Add `/admin/retrieval-quality` route and static UI assets, or extend existing admin shell if route count must stay minimal.
- [ ] Add feedback table, detail panel, review controls, promotion preview, and export controls.
- [ ] Expand eval fixtures with additional deterministic cases.
- [ ] Update README with feedback capture, review, promotion, and eval workflow.
- [ ] Update `product_manuals/README.md` only if manual authors need guidance for feedback/eval hints.
- [ ] Review whether any new durable conventions should be added to `.trellis/spec/backend/`.

## Suggested Implementation Order

1. **Feedback core**
   - Add dataclasses and JSON serialization.
   - Add path safety and text bounds.
   - Add append/list/review overlay functions.
   - Tests first for validation, append/list, missing files, and review status updates.

2. **Search linkage**
   - Add `search_id` generation.
   - Ensure miss and hit responses contain fresh `trace_id`, `search_time_ms`, `cache`, and `search_id`.
   - Add regression tests for cache hit search_id behavior.

3. **Eval promotion**
   - Convert feedback records into existing eval case JSON shape.
   - Add preview skip reasons.
   - Add export with append/overwrite protections.

4. **API and CLI**
   - Wire endpoints thinly over service functions.
   - Add CLI wrappers returning JSON.
   - Add auth and KB allowlist tests.

5. **Admin UI**
   - Add route/template/static JS/CSS.
   - Keep layout dense and operations-focused.
   - Add route/static tests.

6. **Eval fixtures and docs**
   - Expand JSONL suite.
   - Verify `eval run` remains deterministic with hashing embedder.
   - Update README workflows.

## Validation

Focused tests to add/run:

- `uv run pytest tests/unit/test_retrieval_feedback.py -q`
- `uv run pytest tests/unit/test_retrieval_feedback_api.py -q`
- `uv run pytest tests/unit/test_cli.py tests/unit/test_eval_dataset.py tests/unit/test_eval_runner.py -q`
- `uv run pytest tests/unit/test_api.py tests/unit/test_cache.py -q`
- `uv run pytest tests/unit/test_manual_library_ui.py -q` or a new retrieval quality UI test file
- `uv run pytest tests/e2e/test_eval_cli.py -q`

Final full check:

- `uv run pytest tests/ -q`

Optional local UI check:

- Run FastAPI with hashing embedder.
- Open `/admin/retrieval-quality?kb_name=default`.
- Submit a test feedback payload, review it, preview promotion, export JSONL, and run `tagmemorag eval run` against the draft.

## Review Gates

- Before coding: confirm whether MVP uses a new `/admin/retrieval-quality` page or embeds a dialog in `/admin/manual-library`. Recommended: new page.
- Before promotion commit implementation: confirm default output path and whether append is opt-in. Recommended: explicit `append=true` or fail if output exists.
- Before finishing: inspect generated JSONL manually and run eval against it.

## Rollback Points

- Backend feedback capture can ship without admin UI if API/CLI/docs pass.
- Promotion preview can ship before promotion commit/export.
- UI can be read-only list/review before enabling export.
- Removing feedback JSONL/review files restores no-feedback behavior.
