# implement.md - M8 Tag Suggestion UX

## Implementation Checklist

### Phase A - Pre-Development Context

- [x] Read M8 PRD/design/implement.
- [x] Run `python3 ./.trellis/scripts/get_context.py --mode packages`.
- [x] Read backend spec index and relevant backend quality/error/logging guidelines.
- [x] Read shared cross-layer and code-reuse thinking guides.
- [x] Inspect M5 metadata/tag helpers, M6 manual library API, and M7 admin UI code before editing.

### Phase B - Backend Suggestion Helper

- [x] Add `src/tagmemorag/tag_suggestions.py`.
- [x] Define dataclasses or typed models for candidate/suggestion results if useful.
- [x] Reuse `normalize_tag()` from `manuals.py`.
- [x] Implement metadata/path/title/category/model/notes token extraction.
- [x] Implement existing-KB tag collection from managed records and optionally graph facets.
- [x] Implement deterministic scoring, dedupe, exclusion of existing draft tags, stop-word filtering, and limit handling.
- [x] Add focused unit tests for normalization, dedupe, source attribution, existing tag preference, and ordering.

### Phase C - API Endpoint

- [x] Add Pydantic request/response models in `api.py`.
- [x] Add `POST /manuals/tags/suggest`.
- [x] Use `require_scope("search")`, `ensure_kb_access`, and `rate_limit_dep`.
- [x] Load managed records with `list_records(kb_name, settings, graph_state=app_state.kbs.get(kb_name))`.
- [x] Return stable JSON with `kb_name`, `suggestions`, and `existing_tags`.
- [x] Add API tests for success, existing tag exclusion, auth/KB behavior where existing helpers make this practical, and empty library behavior.

### Phase D - Admin UI Integration

- [x] Add suggestion blocks near upload and detail tags textareas in `manual_library.html`.
- [x] Add compact chip/button styling in `manual_library.css`.
- [x] Extend `manual_library.js` with `suggestTags()` fetch helper.
- [x] Build metadata drafts from upload/detail forms without changing existing validation/save behavior.
- [x] Render loading, empty, error, and suggestion states.
- [x] Implement accept-one and accept-all actions with client-side tag dedupe.
- [x] Ensure accepted tags only update the tags textarea and do not auto-save.
- [x] Preserve token/sessionStorage behavior and auth error display.

### Phase E - Docs and Verification

- [x] Update README with endpoint and UI usage.
- [x] Update M8 checklist as work completes.
- [x] Run `uv run pytest tests/unit/test_tag_suggestions.py -q`.
- [x] Run `uv run pytest tests/unit/test_tag_suggestions_api.py tests/unit/test_manual_library_ui.py -q`.
- [ ] Run focused M5/M6/M7 tests:
  - `uv run pytest tests/unit/test_manual_metadata.py tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py -q`
- [ ] Run `uv run pytest tests/ -q`.
- [ ] Smoke test `/admin/manual-library` locally through browser or HTTP-level checks.

## Validation

Expected commands:

```bash
uv run pytest tests/unit/test_tag_suggestions.py -q
uv run pytest tests/unit/test_tag_suggestions_api.py tests/unit/test_manual_library_ui.py -q
uv run pytest tests/unit/test_manual_metadata.py tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py -q
uv run pytest tests/ -q
```

Manual smoke:

1. Start the API server with hashing model/test config if needed.
2. Open `/admin/manual-library`.
3. Open upload dialog and fill source/title/category/model fields.
4. Click `Suggest tags`.
5. Accept one suggestion and confirm it appears in the tags textarea.
6. Validate metadata and confirm server-normalized tags match expectations.
7. Select an existing manual, request suggestions, accept all, and save metadata.
8. Confirm pending rebuild state remains visible and no auto-save happens before Save.

## Review Gates

- [ ] Suggestions are optional and do not persist until upload/save.
- [ ] Backend suggestion logic is deterministic and covered by unit tests.
- [ ] Endpoint does not read large manual files or log raw manual content.
- [ ] Existing validation remains the canonical normalization path.
- [ ] Existing JSON APIs remain backward compatible.
- [ ] Auth and KB allowlist behavior matches nearby manual-library endpoints.
- [ ] UI remains compact and usable on desktop and narrow screens.
- [ ] No frontend build system is introduced.

## Rollback Points

- If suggestion quality is too noisy, ship endpoint behind UI controls but keep upload/edit behavior unchanged.
- If UI integration becomes crowded, keep API and add only one suggestion block in upload first, then detail in a follow-up.
- If deterministic heuristics are insufficient, defer LLM/semantic suggestions to a later task with explicit config and privacy review.
