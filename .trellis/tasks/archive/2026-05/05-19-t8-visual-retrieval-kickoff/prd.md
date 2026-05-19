# T8 Phase 7B visual retrieval kickoff

## Goal

Ship the Phase 7B visual retrieval foundation: visually grounded queries can
retrieve page/region visual assets through a vendor-neutral, default-off visual
candidate path. This task establishes the encoder/reranker/fusion contracts and
deterministic tests; it does not choose or integrate a production visual model.

## User Value

Users ask questions like "where is the reset button?", "show the wiring
diagram", or "find the part labeled drain pump". Text retrieval can attach page
snapshots to text evidence today, but it cannot retrieve a visual asset when the
best signal is visual rather than textual. T8 should create the safe foundation
for that path without making visual model dependencies mandatory.

## Confirmed Facts

- `/retrieve` already returns `visual_evidence` metadata and can attach
  `page_snapshot` / `region_crop` assets to text evidence.
- Existing `VisualEvidenceResolver` only resolves assets for text results; it
  does not generate visual candidates.
- Visual intent detection already exists as non-ranking metadata.
- `DocumentAsset` supports `page_snapshot` and `region_crop`, with safe public
  descriptors that omit storage keys/checksums.
- T7 shipped default-off OCR text ingestion; visual retrieval can build on page
  snapshots and OCR-derived text but must remain a separate path.
- Architecture B7B requires encoder and reranker separation. A visual reranker
  alone is not enough because indexing needs visual candidates.

## Requirements

- Visual retrieval is disabled by default.
- Add a `Settings.visual_retrieval` block with bounded defaults.
- Define vendor-neutral visual candidate and reranker boundaries.
- Ship deterministic local providers for tests; no network, model download, or
  native visual dependency is required in default tests.
- MVP candidate source: existing `DocumentAsset` metadata/manifest, not a real
  embedding index.
- Visual candidates are considered only when visual intent is detected or the
  caller explicitly enables a visual mode.
- Visual candidates must be fused with text results in a deterministic,
  explainable way and must not make text retrieval worse when disabled.
- Public retrieve payloads must not expose storage keys, checksums, local paths,
  vectors, raw image bytes, or model secrets.
- Visual result diagnostics must be low-cardinality counts/reasons only.
- Preserve existing `/search`, `/retrieve`, `/answer`, OCR, and asset behavior
  when visual retrieval is disabled.

## Decisions

### D1 MVP scope: visual-candidate contract, deterministic providers

T8 ships protocol boundaries and deterministic metadata-backed providers. It
does not integrate ColPali, CLIP, DSE, Qwen-VL, or any production visual API.

Reasoning: the storage, fusion, and response contracts must be stable before
choosing costly moving-target models.

### D2 Encoder/reranker handoff

The visual encoder/candidate stage produces `VisualCandidate`s over existing
assets. The visual reranker stage may adjust candidate scores, but it cannot
invent assets that were not produced by the candidate stage.

Reasoning: this preserves B7B's core separation and keeps reranker-only vendor
options from masquerading as visual indexing.

### D3 MVP candidate source

Use page/region asset metadata and optional captions/OCR/nearby text as the
deterministic candidate source. Real visual vectors are deferred.

Reasoning: existing manifests are enough to test data flow, fusion, safety, and
response shape. A future encoder can replace the candidate provider without
changing `/retrieve` shape.

### D4 Fusion stance

When visual retrieval is enabled and intent is visual, merge visual candidates
after text results with score normalization and dedupe by asset/page lineage.
The MVP favors preserving text result order over aggressive visual promotion.

Reasoning: the current eval base is text-heavy. T8 should make visual evidence
available without silently destabilizing existing text relevance.

### D5 Eval stance

Use deterministic unit/API fixtures with page snapshot assets and visual-intent
queries. Do not use LLM-as-judge or live vision models.

Reasoning: default CI must remain offline and reproducible.

## Out Of Scope

- Choosing/integrating a production visual encoder.
- Choosing/integrating a production visual reranker.
- Storing visual vectors or late-interaction indexes.
- Training or finetuning visual models.
- Region detection/cropping beyond assets already present in manifests.
- UI changes for image galleries.
- Visual answer generation; `/answer` can consume retrieve payloads as-is.

## Acceptance Criteria

- [x] `Settings.visual_retrieval` exists and defaults to disabled.
- [x] Visual candidate and reranker protocols exist with deterministic providers.
- [x] Existing `/retrieve` output is unchanged when visual retrieval is disabled.
- [x] Visual-intent `/retrieve` can include deterministic visual-only candidates
      when enabled and asset manifests are present.
- [x] Visual candidates are public-safe: no storage keys, checksums, vectors, raw
      image bytes, or local absolute paths in API responses/debug payloads.
- [x] Visual diagnostics expose bounded counts/reasons.
- [x] Focused tests cover disabled, visual intent enabled, non-visual intent
      skip, missing manifest, dedupe/fusion, and API response shape.
- [x] Existing API, retrieval, OCR, and answer tests remain green.

## Eval Slice

- Synthetic KB with a page snapshot asset whose caption/nearby text matches a
  visual-intent query.
- Query "show reset button diagram" should attach/return the visual candidate.
- Query "how to clean filter" should preserve text-only behavior when intent is
  not visual.
- Existing `/retrieve` and `/answer` regression tests.

## Open Questions

- None blocking implementation; production model/provider selection is deferred.
