# Phase 4 Visual Evidence Asset Pipeline Design

## Architecture Position

This phase sits between parsed/chunked document lineage and future visual evidence responses:

```text
source document
  -> parser/chunker lineage
  -> visual asset extraction
  -> asset store + manifest
  -> authorized asset serving
  -> Phase 5 evidence attachment
```

The goal is not to make retrieval smarter yet. The goal is to preserve visual artifacts in a stable, inspectable, permissioned form so evidence can later reference them.

## Boundaries

In scope:

- Versioned asset metadata contract.
- Local asset store and manifest persistence.
- PDF page snapshot extraction hook with graceful fallback.
- Asset lifecycle primitives.
- Authenticated asset-serving endpoint.
- Debug inventory and metrics/log hooks.

Out of scope:

- OCR, VLM captions, visual embeddings, image vector indexes.
- Returning assets from `/retrieve` evidence.
- Learned visual intent routing.
- Full connector or multi-format visual extraction beyond the PDF snapshot hook.

## Data Contracts

### DocumentAsset

Fields:

- `schema_version`: asset contract version, initially `document_asset.v1`.
- `asset_id`: stable id derived from KB, doc id, asset type, page/bbox, source checksum/version, content checksum when available, and extractor version.
- `kb_name`
- `doc_id`
- `source_file`
- `source_version`
- `type`: `source_file | embedded_image | page_snapshot | region_crop | table_snapshot | ocr_layer`
- `mime_type`
- `storage_backend`: `local | s3`
- `storage_key`: safe relative object key, never a local absolute path or signed URL.
- `page_number`
- `bbox`
- `width`
- `height`
- `checksum`
- `caption`
- `nearby_text`
- `ocr_text`
- `metadata`
- `status`: `ready | missing | failed | deleted`
- `failure_reason`
- `created_at`
- `updated_at`
- `extractor_name`
- `extractor_version`

### Asset Manifest

Per KB manifest path:

```text
data/{kb_name}/assets/asset_manifest.json
```

Fields:

- `schema_version`
- `kb_name`
- `updated_at`
- `assets`: asset id to metadata mapping
- `stats`: counts by type/status/backend

The manifest stores no raw document text, vectors, full local paths, credentials, or signed URLs.

## Stable ID Strategy

- `doc_id` comes from chunk lineage metadata where available.
- `asset_id` is deterministic:
  - namespace: `asset`
  - `kb_name`
  - `doc_id`
  - normalized `source_file`
  - `source_version` or source checksum when available
  - `asset_type`
  - page number
  - bbox when applicable
  - extractor name/version
  - content checksum when extraction produced bytes
- If extraction fails before bytes exist, the failed record may use the same deterministic logical id without content checksum.
- Rebuilds reuse IDs for unchanged source/version/page assets.
- A changed extractor version is allowed to produce new IDs so old citations can remain traceable.

## Storage

Add a narrow `document_assets.py` or similarly scoped module instead of overloading manual source blob storage. It may reuse safe-key helpers and atomic-write patterns, but the concept is separate:

- Manual blob store stores original uploaded sources.
- Asset store stores derived or evidence-facing artifacts.

Local storage root defaults to:

```text
data/document_assets
```

Safe key shape:

```text
{kb}/{doc_id}/{asset_type}/{asset_id}.{ext}
```

S3-compatible implementation may be deferred, but the metadata contract must keep `storage_backend` and `storage_key` backend-agnostic.

## Extraction

Initial extraction is PDF page snapshots where feasible. Implementation may choose the lightest available library path already compatible with the project. If no renderer is installed or a PDF page fails:

- record a bounded failure reason,
- continue rebuild/search compatibility,
- surface failure counts in inspect/debug,
- do not fail the whole KB unless a future strict config is added.

Config should disable snapshot extraction by default or keep it opt-in if the renderer dependency is not guaranteed. If enabled and unavailable, degrade cleanly.

## API

Add an authenticated asset endpoint such as:

```text
GET /assets/{asset_id}?kb_name=...
```

Contract:

- Requires authenticated scope, initially `search`.
- Calls `ensure_kb_access` for the requested KB.
- Looks up the asset manifest in that KB.
- Serves only `status=ready` assets.
- Returns structured `INVALID_REQUEST` / `STORAGE_LOAD_FAILED` errors for missing manifest/object.
- Does not accept arbitrary storage keys from clients.
- Does not return local absolute paths or signed object internals.

Future signed URLs can be layered behind the same authorization check.

## Lifecycle

First implementation should include primitives even if not all are wired to every caller:

- Replace assets for a document version during rebuild while keeping manifest consistency.
- Mark or remove assets for deleted/disabled documents.
- Cleanup orphan storage objects not referenced by the manifest.
- Cleanup temp extraction outputs on failed rebuild.
- Verify manifest assets exist in the configured store.
- Deduplicate identical content by checksum when practical.

## Observability and Debug

Expose safe summaries:

- total asset count
- counts by type/status/backend
- extraction attempted/skipped/failed counts
- bounded failure reason codes
- storage verification missing count

Never expose raw text, query text, vectors, local absolute paths, credentials, or signed URL query strings in logs/debug.

## Compatibility

- Existing `Chunk.metadata["asset_refs"]` may remain empty in this phase unless extraction is naturally tied to a document rebuild.
- `/search` shape remains unchanged.
- `/retrieve` may continue returning no asset objects until Phase 5.
- Old data directories without asset manifests load as empty asset inventories.

## Evaluation Gate

This phase changes ingestion/storage, not ranking. Required gates:

- Existing search/retrieve eval baselines must not regress.
- Unit tests prove old client response compatibility.
- Asset extraction fixtures prove success/failure behavior without requiring network or heavyweight external services.
- Any intentional extractor dependency limitation is documented in implementation notes.

