# Phase 4 Visual Evidence Asset Pipeline Implementation Plan

## Scope Guard

Implement the asset foundation only. Do not attach assets to `/retrieve` evidence and do not add OCR, VLM captions, visual embeddings, or visual reranking.

## Checklist

- [x] Review current manual blob store, registry, auth dependencies, parser lineage, and API error patterns.
- [x] Add asset config with backward-compatible defaults.
- [x] Add `DocumentAsset` contract and manifest load/save helpers.
- [x] Add local asset store with atomic writes, safe relative keys, get/delete/exists/verify helpers.
- [x] Add stable asset id derivation and bounded failure reason helpers.
- [x] Add PDF page snapshot extraction hook behind config with graceful fallback when renderer/dependency is unavailable.
- [x] Add lifecycle primitives: replace document assets, mark/remove deleted or disabled assets, orphan cleanup, and consistency verification.
- [x] Add authenticated asset-serving endpoint that authorizes by KB and manifest lookup, never by arbitrary path.
- [x] Add inspect/debug summary helper for asset inventories and extraction failures.
- [x] Add focused tests for schema, storage safety, manifest compatibility, extraction fallback, lifecycle, asset-serving auth, and `/search`/`/retrieve` compatibility.
- [x] Run focused tests.
- [x] Run full tests or the relevant broad suite.
- [x] Run eval CI and record baseline outcome.
- [x] Update this implementation checklist with validation results.

## Validation Results

- `2026-05-17`: `.venv/bin/python -m pytest tests/unit/test_document_assets.py tests/unit/test_config_env.py tests/unit/test_api.py -q` passed: 47 passed.
- `2026-05-17`: `.venv/bin/python -m pytest tests/ -q` passed: 513 passed, 2 skipped.
- `2026-05-17`: `.venv/bin/python scripts/run_eval_ci.py` passed all 8 eval suites against `hashing.json`.
- `2026-05-17`: `git diff --check` passed.

## Implementation Notes

- `pymupdf/fitz` is treated as an optional renderer. When unavailable and PDF page snapshots are enabled, extraction records `renderer_unavailable` and continues unless `assets.strict_extraction=true`.
- Phase 4 stores and serves assets, but `/retrieve` remains text-only. Attaching visual assets to evidence is intentionally deferred to Phase 5.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/unit/test_document_assets.py tests/unit/test_api.py tests/unit/test_config_env.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
git diff --check
.venv/bin/python .trellis/scripts/task.py validate .trellis/tasks/05-17-visual-evidence-asset-pipeline
```

## Rollback

- Disable asset extraction through config.
- Keep `/assets/{asset_id}` unavailable or serving only existing ready manifest entries.
- Existing search/retrieve behavior remains text-only and should continue working without an asset manifest.
