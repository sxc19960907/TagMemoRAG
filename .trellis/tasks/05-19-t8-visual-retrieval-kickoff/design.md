# T8 Phase 7B visual retrieval kickoff — Design

## Scope

Add a default-off visual retrieval foundation over existing document assets.
The MVP is metadata-backed and deterministic: it proves candidate generation,
rerank boundary, fusion, and public response shape without adding real visual
model dependencies.

## Module Layout

```text
src/tagmemorag/visual_retrieval/
  __init__.py
  base.py
  provider.py
```

- `base.py`: `VisualCandidate`, `VisualQueryContext`, `VisualCandidateProvider`,
  `VisualReranker`, `VisualRetrievalSummary`.
- `provider.py`: deterministic manifest-backed candidate provider and noop
  reranker/factory.
- `config.py`: `VisualRetrievalConfig`.
- `retrieval.py`: optional visual candidates in retrieve response assembly.
- `api.py`: route-level wiring from settings/state manifest into retrieval.

## Config

```yaml
visual_retrieval:
  enabled: false
  provider: deterministic
  reranker: noop
  trigger: visual_intent
  max_candidates: 4
  min_score: 0.1
```

Provider values in T8: `deterministic`. Reranker values in T8: `noop`.

## Candidate Contract

The candidate provider receives:

- query text
- detected visual intent
- KB name
- `AssetManifest`
- max candidates

It returns `VisualCandidate`s referencing ready `page_snapshot` or `region_crop`
assets. Candidates contain safe metadata only: asset id, doc id, source file,
page number, score, reason, provider, and version.

The deterministic provider scores assets by token overlap against caption,
nearby text, OCR text, source file, and low-cardinality metadata text. It does
not inspect image bytes.

## Reranker Contract

The reranker receives query plus candidates and returns adjusted candidates. The
noop reranker preserves order and score. A future visual reranker can replace it
without changing candidate generation.

## Retrieve Fusion

When visual retrieval is disabled, retrieve response shape remains unchanged.

When enabled and visual intent is detected:

1. Build text evidence as today.
2. Generate and rerank visual candidates from the asset manifest.
3. Deduplicate candidates already attached to text evidence.
4. Append visual-only evidence records after text evidence, up to configured
   limits.
5. Context pack includes visual candidate asset refs with compact content such
   as the caption/nearby text placeholder. Raw image data is never embedded.

Visual-only evidence gets `content_type="visual_asset"` in context items and a
reason indicating visual candidate selection.

## Safety

Public payloads use existing asset descriptors and must not include storage
keys, checksums, local paths, raw bytes, vectors, or secrets. Diagnostics are
counts and bounded reasons only.

## Tests

- Config defaults and override.
- Deterministic provider token overlap.
- Retrieval disabled unchanged.
- Visual intent enabled adds visual-only evidence.
- Non-visual intent skips visual candidate path.
- Missing manifest records bounded omission.
- Existing API/retrieve/answer/OCR tests remain green.
