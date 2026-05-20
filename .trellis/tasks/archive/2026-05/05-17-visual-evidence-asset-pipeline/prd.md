# Phase 4 visual evidence asset pipeline

## Goal

Implement the first production-grade visual evidence asset layer for TagMemoRAG without changing the `/retrieve` evidence contract yet.

This phase should make non-text document artifacts first-class, permissioned, stored objects that later phases can attach to evidence. The immediate target is PDF page snapshots and asset serving foundations, not OCR, visual embedding, multimodal ranking, or full visual evidence selection.

## Requirements

- Add a versioned `DocumentAsset`-like metadata contract for derived visual artifacts.
- Add a storage abstraction for visual evidence assets that supports local storage now and leaves an S3-compatible path open without duplicating the manual source blob store concept.
- Generate PDF page snapshot assets where feasible, controlled by config and safe failure behavior.
- Persist asset manifests using stable IDs so assets can be reused or cleaned up across rebuilds.
- Add an asset-serving endpoint that authorizes access against the same KB/document context that produced the evidence.
- Keep `/search` compatible and do not add visual assets to `/retrieve` yet; Phase 5 owns evidence attachment.
- Add inspect/debug-friendly summaries that expose counts, asset types, and failure reasons without leaking raw document text, unsafe paths, secrets, or signed storage internals.
- Define lifecycle behavior for deleted/disabled documents, rebuild replacement, failed rebuild temp assets, orphan cleanup, checksum deduplication, retention, and local/S3 consistency checks.
- Preserve the product-manual-first path while keeping contracts generic for broader document types.
- Follow the roadmap-wide production requirements: schema compatibility, eval/baseline gate, observability/debug, security/permissions, and failure degradation.

## Acceptance Criteria

- [ ] Asset metadata schema is versioned and includes `asset_id`, `doc_id`, `type`, `mime_type`, `storage_uri` or safe store key, `page_number`, `bbox`, `width`, `height`, `checksum`, captions/text placeholders, source lineage, and lifecycle fields.
- [ ] Asset IDs are stable across rebuilds when the same document version and page-derived content are unchanged.
- [ ] Local asset storage writes are atomic and path-safe; S3-compatible design remains explicit even if full S3 implementation is deferred.
- [ ] PDF page snapshot extraction can be enabled per config/profile and records graceful failures instead of breaking rebuilds.
- [ ] Asset manifest persistence supports load/save, version validation, replacement, orphan detection, and cleanup primitives.
- [ ] Asset-serving endpoint requires an authenticated scope and KB allowlist access, and it never serves assets outside the authorized KB/document context.
- [ ] `/search` and `/retrieve` existing response shapes remain backward-compatible.
- [ ] Debug/inspect output reports asset inventory and extraction/store failures without raw snippets, local absolute paths, query text, vectors, or secrets.
- [ ] Tests cover schema round trip, safe path handling, PDF extraction fallback, asset serving auth, disabled/deleted document access behavior, and old client compatibility.
- [ ] Focused tests, full unit tests, and eval CI pass or documented intentional trade-offs are recorded.

## Notes

- This is Phase 4 only. Do not implement OCR, VLM captioning, visual embeddings, table snapshot ranking, or `/answer`.
- Phase 5 will attach these assets to `/retrieve` evidence after this storage and serving foundation is stable.
