# Phase 5 Visual Evidence Retrieve API Design

## Architecture Position

Phase 5 connects the Phase 4 asset foundation to the Phase 3 `/retrieve` evidence contract:

```text
search results
  -> text evidence builder
  -> asset manifest lookup by chunk lineage
  -> evidence.assets descriptors
  -> context_pack asset refs
  -> safe debug / inspect summaries
```

This is evidence attachment, not visual retrieval. Ranking still comes from the existing text/vector/lexical/metadata/graph pipeline.

## Boundaries

In scope:

- Additive `assets` field on `/retrieve` evidence.
- Safe asset descriptors and authorized asset URLs.
- Page-level matching from chunk lineage to `page_snapshot` assets.
- Optional use of existing `asset_refs` when present.
- Visual-oriented query intent flags using deterministic rules.
- Debug summaries for attach/omit reasons.
- Compatibility and permission tests.

Out of scope:

- OCR text generation.
- VLM captions.
- Visual embeddings or image vector index.
- Region crop generation if no bbox data is already available.
- Learned fusion or visual-score reranking.
- `/answer`.

## Data Flow

1. `/retrieve` executes search as today.
2. `build_retrieve_response()` receives results and, in this phase, an optional asset resolver/context.
3. For each result:
   - read `metadata.doc_id`, `metadata.page_start`, `metadata.page_end`, `metadata.asset_refs`, `source_file`;
   - query the loaded `AssetManifest`;
   - attach ready assets that match the evidence lineage;
   - produce safe omit reasons for missing/failed/deleted/unmatched assets.
4. Context pack stays text-first but may include `asset_refs` for Agents/UI clients.
5. Debug inspect reports counts and omit reasons, not raw storage keys or text.

## API Contract

Existing `/retrieve` fields remain stable. Additive fields:

```json
{
  "evidence": [
    {
      "evidence_id": "ev_001",
      "assets": [
        {
          "asset_id": "asset:sha256:...",
          "type": "page_snapshot",
          "url": "/assets/asset:sha256:...?kb_name=default",
          "mime_type": "image/png",
          "page_number": 12,
          "bbox": null,
          "width": 1240,
          "height": 1754,
          "caption": "",
          "alt_text": "Page 12 snapshot for citation cit_001",
          "source": {
            "doc_id": "manual-1",
            "source_file": "manual.pdf",
            "page_range": [12, 12]
          }
        }
      ],
      "asset_warnings": []
    }
  ],
  "context_pack": {
    "items": [
      {
        "content_type": "text",
        "asset_refs": ["asset:sha256:..."]
      }
    ]
  }
}
```

Rules:

- `assets` defaults to `[]`.
- `asset_warnings` defaults to `[]`.
- `url` is a service URL routed through the authorized asset endpoint.
- Do not return `storage_key`, local absolute path, bucket name, signed URL internals, checksum, or storage backend details in evidence.
- Debug can include aggregate reason codes and asset ids, but not storage internals.

## Asset Matching

Matching priority:

1. Explicit `metadata.asset_refs` if populated and present in the manifest.
2. Same `doc_id` and overlapping page range for page-level assets.
3. Same `source_file` and page range when `doc_id` is missing.

Initial asset type support:

- `page_snapshot`: attach when `asset.page_number` is within `page_start..page_end`.
- `region_crop`: future-compatible; only attach when bbox/page metadata exists and asset is already present.
- `embedded_image` / `table_snapshot`: future-compatible; do not infer broad matching unless `asset_refs` explicitly point to them.
- `ocr_layer`: do not attach as visual evidence in this phase.

Limits:

- Cap attached assets per evidence item with a small config/default, for example `max_assets_per_evidence=3`.
- Prefer page snapshots closest to the evidence page range.
- Do not read binary asset bytes during `/retrieve`; only manifest metadata and URL construction are needed.

## Query Intent

Add a minimal, rule-based visual intent flag:

- English hints: `show`, `diagram`, `image`, `picture`, `photo`, `button`, `where is`, `layout`.
- Chinese hints: `图`, `图片`, `示意图`, `按钮`, `位置`, `在哪`, `长什么样`, `给我看`.

Use this only for:

- debug/inspect visibility,
- allowing future preference for assets,
- warnings when query appears visual but no assets are available.

Do not change ranking in this phase based on visual intent.

## Permission Model

- `/retrieve` already requires `search` scope and `ensure_kb_access`.
- Asset descriptors are produced only from the requested KB manifest.
- Wrong-KB assets are ignored even if an id appears in `asset_refs`.
- Asset URLs must use `asset_id` and `kb_name`; serving still re-checks auth when requested.
- Debug output must not reveal omitted wrong-KB storage details.

## Failure Degradation

Cases:

- No manifest: `assets=[]`, warning/debug reason `asset_manifest_missing`.
- No matching assets: `assets=[]`, reason `no_matching_assets`.
- Matching asset is `failed/deleted/missing`: omit and record status reason.
- Ready asset missing from storage: do not check storage by default during `/retrieve`; Phase 4 inspect/verify handles storage health. If explicitly verified in debug mode and missing, record `asset_object_missing`.
- Asset URL construction failure: omit asset, record `asset_url_failed`.

Text evidence must still be returned.

## Observability / Debug

Safe counters:

- evidence count with assets
- attached asset count
- omitted by reason
- visual intent detected
- manifest present/missing

`retrieve_inspect_payload()` can add:

```json
{
  "visual_evidence": {
    "intent": "visual_reference",
    "attached_count": 2,
    "evidence_with_assets": 1,
    "omitted": {"no_matching_assets": 3}
  }
}
```

No raw text, query tokens, storage keys, local paths, vectors, or signed URLs.

## Compatibility

- Existing `/retrieve` clients can ignore `assets` and `asset_warnings`.
- Existing `/search` remains unchanged.
- Existing eval baselines should remain stable because ranking and text context are unchanged.
- Old KBs without asset manifests continue returning text-only evidence.

## Evaluation Gate

Required checks:

- Unit: attach page snapshot by doc/page lineage.
- Unit: explicit `asset_refs` attach only same-KB ready assets.
- Unit/API: missing manifest and missing matching assets degrade to text-only.
- Unit/API: unauthorized KB cannot access asset descriptors through `/retrieve`.
- Unit: `/search` response shape unchanged.
- Unit: inspect/debug visual summary has no raw text/storage internals.
- Full tests and eval CI pass with no ranking baseline regression.

