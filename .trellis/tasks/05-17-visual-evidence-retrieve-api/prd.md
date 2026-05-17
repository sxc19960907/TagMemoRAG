# Phase 5 visual evidence retrieve API

## Goal

Extend the Agent-facing `/retrieve` API so text evidence can carry authorized visual asset references from the Phase 4 asset manifest.

This phase turns stored page snapshots and future asset types into evidence attachments that upper-layer Agents and UIs can use for human-friendly, traceable answers. It must stay additive and backward-compatible: existing text-only clients keep working, and missing assets degrade to text evidence.

## Requirements

- Attach visual assets to `/retrieve` evidence when assets are relevant to the matched chunk lineage.
- Start with existing Phase 4 asset types, especially `page_snapshot`; leave region crops, embedded images, table snapshots, OCR layers, and visual embeddings as optional/future-compatible fields.
- Return safe asset descriptors, not storage internals: `asset_id`, `type`, authorized URL/path, `mime_type`, `page_number`, `bbox`, dimensions, caption/alt text if available, and fallback reason when omitted.
- Preserve `/retrieve` schema compatibility through additive fields only.
- Preserve `/search` compatibility; `/search` must not start returning visual evidence.
- Enforce the same KB/document permission context used by retrieval. Unauthorized assets must never appear in evidence or debug payloads.
- Add visual evidence debug/inspect output explaining attached, omitted, missing, or unauthorized assets without raw document text, local absolute paths, storage keys, signed URL internals, query text, or vectors.
- Add minimal visual intent handling for visual-oriented queries such as "show diagram", "where is part", "find button", and Chinese equivalents, using rules only. Do not add LLM-based intent classification yet.
- Define fallback behavior when no asset manifest exists, no matching asset exists, an asset is missing from storage, or asset serving is disabled.
- Define latency budget and bounded asset lookup behavior so `/retrieve` does not become asset-store heavy.
- Add eval/test coverage for visual evidence attachment correctness, missing-asset degradation, permission filtering, and old text-only compatibility.

## Acceptance Criteria

- [ ] `/retrieve` evidence items include an additive `assets` list when matching ready assets are available.
- [ ] `/retrieve` citations or source metadata can reference page-level assets without breaking existing citation fields.
- [ ] Context pack remains text-first; assets may be represented as references/metadata but not large binary payloads.
- [ ] Asset URLs are generated through the authorized asset endpoint, not by exposing local paths or storage keys.
- [ ] Asset matching uses chunk lineage (`doc_id`, `page_start/page_end`, `asset_refs`, `source_file`) and does not rely on domain-specific appliance keywords.
- [ ] Missing manifests/assets produce explicit warnings or debug omit reasons while preserving text evidence.
- [ ] Unauthorized or wrong-KB assets are filtered and covered by tests.
- [ ] `/search` response shape remains unchanged.
- [ ] Debug inspect payload includes safe visual evidence counts and omit reasons.
- [ ] Focused unit tests, full tests, eval CI, and `git diff --check` pass, or intentional trade-offs are documented.

## Notes

- This is Phase 5 only. Do not implement OCR, VLM captioning, visual embedding, learned fusion, or `/answer`.
- Phase 4 already introduced `DocumentAsset`, manifest persistence, local asset storage, and `GET /assets/{asset_id}`.
- Phase 6 remains optional `/answer`; Phase 7 owns OCR/visual retrieval.
