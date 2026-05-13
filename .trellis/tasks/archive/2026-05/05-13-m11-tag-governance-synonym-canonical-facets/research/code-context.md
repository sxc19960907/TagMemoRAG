# M11 Code Context

## Existing Tag Flow

- `src/tagmemorag/manuals.py`
  - Owns `ManualMetadata.tags` and `normalize_tag()`.
  - Current normalization is lower-kebab-case and should remain the canonical normalization primitive.

- `src/tagmemorag/manual_library.py`
  - Owns managed library root resolution, safe source paths, sidecar-backed records, metadata validation, upload/update/delete, and pending rebuild markers.
  - M11 should store `.tagmemorag-tags.json` under the same per-KB library root and reuse existing atomic write patterns.

- `src/tagmemorag/tag_suggestions.py`
  - Uses draft metadata, existing managed records, and loaded graph facets to produce deterministic suggestions.
  - M11 should add optional policy-aware canonicalization here instead of creating a second suggestion path.

- `src/tagmemorag/wave_searcher.py`
  - Normalizes tag filters and checks graph node metadata tags.
  - M11 should resolve synonyms before calling search to avoid coupling the algorithm layer to manual-library policy storage.

- `src/tagmemorag/manual_bulk_import.py`
  - Powers M10 CSV/JSON/JSONL parsing, validation preview, and commit.
  - M11 should surface governance warnings/errors in this preview rather than building another batch validation path.

- `src/tagmemorag/api.py`
  - Central route layer for manual metadata validation, tag suggestions, bulk import, and admin UI.
  - New endpoints should follow existing auth dependencies and structured `ServiceError` responses.

- `src/tagmemorag/web/templates/manual_library.html` and `src/tagmemorag/web/static/manual_library.js/css`
  - Existing operations UI is server-rendered shell plus vanilla JS.
  - M11 should extend this UI without adding a frontend build step.

## Production Constraints

- No policy file must mean legacy behavior.
- Policy writes and sidecar rewrites must be atomic and constrained to the manual library root.
- Mutating tag rewrites must mark pending rebuild and must not change currently served search results until rebuild.
- Metrics/log labels must not include raw tags; raw tags are high-cardinality.
- Preview-first workflow is required before broad sidecar mutation.
