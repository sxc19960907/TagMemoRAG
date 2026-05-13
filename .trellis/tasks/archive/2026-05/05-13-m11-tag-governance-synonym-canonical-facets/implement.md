# implement.md - M11 Tag Governance, Synonyms, and Drift Analytics

## Implementation Checklist

- [ ] Read current backend specs with `trellis-before-dev` before coding.
- [ ] Add `tag_governance.py` with policy dataclasses, load/save, validation, and serialization.
- [ ] Implement `.tagmemorag-tags.json` policy path under each managed KB library root.
- [ ] Implement tag resolution rules: canonical, synonym, deprecated replacement, unknown, no-policy fallback.
- [ ] Implement synonym cycle detection and invalid target validation.
- [ ] Implement tag usage stats from `manual_library.list_records()` plus optional loaded `GraphState`.
- [ ] Implement drift detection for unknown tags, synonyms in use, deprecated tags, likely duplicates, and graph/library drift.
- [ ] Implement governance validation messages for metadata tags.
- [ ] Integrate governance checks into `POST /manuals/validate`.
- [ ] Integrate governance checks into M10 `manual_bulk_import.preview_bulk_import()`.
- [ ] Update `tag_suggestions.suggest_tags()` to prefer canonical tags and suppress deprecated tags.
- [ ] Resolve search filter tag synonyms at API and CLI boundaries before `wave_search()`.
- [ ] Implement merge/rename preview contracts.
- [ ] Implement merge/rename commit with atomic per-sidecar metadata updates and pending rebuild marker.
- [ ] Add tag governance API endpoints:
  - [ ] `GET /manual-library/tags`
  - [ ] `PUT /manual-library/tags/policy`
  - [ ] `POST /manual-library/tags/rewrite/preview`
  - [ ] `POST /manual-library/tags/rewrite`
- [ ] Enforce auth:
  - [ ] read/search scope for stats and preview
  - [ ] rebuild/admin-equivalent write scope for policy updates and rewrite commit
  - [ ] KB allowlist access on all endpoints
- [ ] Add thin CLI helpers for stats, policy validation, rewrite preview, and rewrite commit.
- [ ] Extend `/admin/manual-library` with Tag Governance controls:
  - [ ] tag facets table
  - [ ] drift issue table
  - [ ] policy editor or JSON policy pane
  - [ ] rewrite form
  - [ ] rewrite preview/commit controls
- [ ] Update README and `product_manuals/README.md` with policy template and governance workflow.
- [ ] Add tests for policy parsing/validation, stats, drift, validation integration, suggestions, search filter resolution, rewrite preview/commit, API auth, CLI, and UI route/static behavior.
- [ ] Review whether any new durable conventions should be added to `.trellis/spec/backend/`.

## Suggested Implementation Order

1. **Policy core**
   - Add dataclasses and JSON load/save.
   - Add policy normalization, cycle detection, and `resolve_tag()`.
   - Tests first: missing policy, valid policy, invalid cycle, invalid target.

2. **Stats and drift**
   - Build usage stats from managed records.
   - Add graph comparison when graph state exists.
   - Add conservative drift heuristics.

3. **Validation and suggestion integration**
   - Keep no-policy behavior unchanged.
   - Add governance messages to manual validation and bulk preview.
   - Canonicalize suggestion candidates through policy.

4. **Search filter integration**
   - Resolve API `SearchFilters.tags` before search.
   - Resolve CLI `--tag` values before search.
   - Add regression tests for synonym filter matching.

5. **Rewrite preview/commit**
   - Implement preview against sidecar records.
   - Implement commit by updating sidecar metadata, deduping tags, and marking pending.
   - Add idempotency and partial failure tests.

6. **API and CLI**
   - Wire endpoints thinly over service functions.
   - Add structured error responses and safe logs.
   - Add CLI wrappers over the same service functions.

7. **Admin UI and docs**
   - Add dense operations UI controls.
   - Add route/static tests.
   - Update docs.

## Validation

Focused tests to add/run:

- `uv run pytest tests/unit/test_tag_governance.py -q`
- `uv run pytest tests/unit/test_tag_governance_api.py -q`
- `uv run pytest tests/unit/test_tag_suggestions_api.py tests/unit/test_manual_bulk_import.py -q`
- `uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_cli.py -q`

Final full check:

- `uv run pytest tests/ -q`

Optional local UI check:

- Run FastAPI with hashing embedder.
- Open `/admin/manual-library?kb_name=default`.
- Verify tag facets, drift rows, policy validation, rewrite preview, and commit state.

## Review Gates

- Before coding: confirm whether policy MVP uses JSON editor in admin UI or fully structured table editing. Recommended MVP: JSON editor plus focused stats/drift/rewrite tables.
- Before commit implementation: verify whether source tags should become synonyms or deprecated aliases by default after merge. Recommended default: synonym for merge, deprecated for rename only when requested.
- Before finishing: manually inspect a KB with:
  - canonical tag in use
  - synonym tag in use
  - deprecated tag in use
  - unknown tag
  - graph/library drift after sidecar update before rebuild

## Rollback Points

- Policy service can ship without UI if API/CLI/docs pass.
- UI can expose read-only stats/drift before enabling rewrite commit.
- No database migration is required.
- Removing `.tagmemorag-tags.json` restores legacy no-policy behavior.
- Sidecar rewrite rollback can be handled by VCS/backup restore or inverse rewrite followed by rebuild.
