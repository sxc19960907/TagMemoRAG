# Phase 5 Visual Evidence Retrieve API Implementation Plan

## Scope Guard

Only attach already-stored visual assets to `/retrieve` evidence. Do not implement OCR, VLM captions, visual embeddings, image ranking, crop generation, or `/answer`.

## Implementation Checklist

- [x] Review Phase 4 `document_assets.py`, `/assets/{asset_id}`, and current `retrieval.py` evidence builder.
- [x] Add a small asset resolution contract for `/retrieve`, likely independent from FastAPI so it can be unit-tested.
- [x] Load asset manifest in `_retrieve_impl` after KB access is authorized.
- [x] Extend `build_retrieve_response()` with optional asset resolver/manifest context while preserving current call compatibility.
- [x] Add `assets` and `asset_warnings` to each evidence item as additive fields.
- [x] Add `asset_refs` to context-pack items as additive fields.
- [x] Add safe asset descriptor builder that emits authorized `/assets/{asset_id}?kb_name=...` URLs and hides storage internals.
- [x] Implement matching by explicit `asset_refs`, then `doc_id` + page range, then source file + page range.
- [x] Add minimal rule-based visual intent summary without changing ranking.
- [x] Extend `retrieve_inspect_payload()` with safe visual evidence counters and omit reasons.
- [x] Add tests for page snapshot attachment, explicit asset refs, missing manifest fallback, wrong-KB filtering, debug safety, `/search` compatibility, and `/retrieve` backward compatibility.
- [x] Run focused tests.
- [x] Run full tests.
- [x] Run eval CI and confirm no ranking baseline regression.
- [x] Run `git diff --check`.
- [x] Validate the Trellis task.
- [x] Update this checklist with validation results.

## Validation Results

- `2026-05-17`: `.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_api.py tests/unit/test_document_assets.py -q` passed: 37 passed.
- `2026-05-17`: `.venv/bin/python -m pytest tests/ -q` passed: 519 passed, 2 skipped.
- `2026-05-17`: `.venv/bin/python scripts/run_eval_ci.py` passed all 8 eval suites against `hashing.json`.
- `2026-05-17`: `git diff --check` passed.
- `2026-05-17`: `.venv/bin/python .trellis/scripts/task.py validate .trellis/tasks/05-17-visual-evidence-retrieve-api` passed.

## Implementation Notes

- Asset attachment is additive: existing text evidence fields and `/search` shape remain unchanged.
- `/retrieve` now reports `visual_evidence` summary and per-evidence `assets` / `asset_warnings`; context items include `asset_refs`.
- Visual intent is rule-based metadata only and does not affect retrieval ranking.
- Evidence descriptors expose `/assets/{asset_id}?kb_name=...` URLs and intentionally omit storage keys, checksums, local paths, and binary content.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_api.py tests/unit/test_document_assets.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
git diff --check
.venv/bin/python .trellis/scripts/task.py validate .trellis/tasks/05-17-visual-evidence-retrieve-api
```

## Review Gates

- Confirm `/retrieve` remains additive and text-first.
- Confirm `/search` is untouched.
- Confirm no storage keys, local paths, raw query text, or binary content appear in evidence/debug.
- Confirm visual intent does not change ranking in this phase.

## Rollback

- Disable asset attachment by not passing an asset resolver/manifest to `build_retrieve_response()`.
- Existing text-only `/retrieve` shape remains valid because all new fields are additive.
