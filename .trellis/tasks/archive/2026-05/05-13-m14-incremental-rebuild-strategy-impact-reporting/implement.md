# implement.md - M14 Incremental Rebuild Strategy and Impact Reporting

## Implementation Checklist

- [ ] Read current backend specs with `trellis-before-dev` before coding.
- [ ] Add config fields for `auto` thresholds with safe defaults.
- [ ] Add chunk identity dataclasses and JSON persistence helpers.
- [ ] Save a chunk identity map after successful full and incremental managed-library rebuilds.
- [ ] Load and validate chunk identity map during incremental rebuild.
- [ ] Compute dirty chunk identities after parsing dirty active manuals.
- [ ] Reuse vectors for unchanged dirty-manual chunks when identity matches.
- [ ] Embed only new/changed dirty chunks.
- [ ] Preserve existing M13 manual-level reuse for non-dirty manuals.
- [ ] Add fallback reasons for identity-map missing/corrupt/ambiguous/parser-changed cases.
- [ ] Implement threshold-based `auto` mode decision.
- [ ] Add `auto_decision_reason` to `RebuildTask`, task response, and `meta.json`.
- [ ] Add rebuild impact report dataclasses and compact serialization.
- [ ] Persist the latest impact report after successful managed-library rebuild.
- [ ] Include impact summary in rebuild task responses.
- [ ] Add API dirty export endpoint.
- [ ] Add CLI `manual-library dirty` helper returning JSON and optionally CSV.
- [ ] Extend admin UI only if a compact summary fits cleanly; avoid a large diff viewer.
- [ ] Update README with auto mode, dirty export, and impact report examples.
- [ ] Update backend spec if chunk identity or impact report file contracts become durable.

## Validation

Focused tests:

- `uv run pytest tests/unit/test_manual_library.py -q`
- `uv run pytest tests/unit/test_incremental_rebuild.py -q`
- `uv run pytest tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_cli.py -q`
- `uv run pytest tests/unit/test_manual_library_ui.py -q`

Final check:

- `uv run pytest tests/ -q`

## Review Gates

- Confirm identity-map location before implementation.
- Confirm `auto` thresholds are conservative and do not change default rebuild behavior.
- Verify impact reports never include raw chunk text.
- Verify failed rebuilds do not replace identity or impact artifacts.

## Rollback Points

- Ship dirty export and impact report before chunk-level reuse if needed.
- Keep chunk identity map write-only initially if reuse validation is not strong enough.
- Disable `auto` threshold selection by using `mode=full` or `mode=incremental` explicitly.
