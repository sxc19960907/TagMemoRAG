# PDF page preview readiness and QA source opening design

## Boundary

This task improves readiness reporting and user-facing fallback copy for PDF page previews. It does not add a full PDF viewer, raw document download, or direct exposure of storage internals.

## Data flow

1. Asset extraction continues to create page snapshot assets when `assets.enabled` and `assets.pdf_page_snapshots_enabled` are enabled and PyMuPDF is available.
2. The latest KB graph metadata and asset manifest summary are reduced to a sanitized `source_preview` diagnostics object.
3. Manual Library diagnostics expose that object under `last_rebuild.source_preview`.
4. RAG Readiness reads the same diagnostics and adds source preview status to the Manual Library card details plus a specific recommendation when review is needed.
5. QA source cards keep using evidence-provided safe `/assets/{asset_id}` URLs. If no valid URL exists, the card renders a bounded fallback reason from safe warning/status fields or from the existing generic fallback.

## Contracts

`source_preview` may contain:

- `enabled`: whether document assets are enabled.
- `pdf_page_snapshots_enabled`: whether PDF snapshots are configured.
- `renderer`: public renderer label, currently `pymupdf`.
- `renderer_available`: boolean command/import availability signal.
- `status`: `ready`, `needs_review`, or `disabled`.
- `pdf_documents`: count from PDF quality metadata.
- `page_snapshots_ready`: ready page snapshot count.
- `page_snapshots_failed`: failed page snapshot count.
- `failure_reasons`: bounded reason counts.
- `message`: user/admin-facing summary.

The object must not contain storage keys, local paths, blob keys, checksums, node ids, or raw manifest records.

## Compatibility

When no PDFs exist, source preview is informational and should not create a readiness warning. When PDFs exist but snapshots are disabled or the renderer is unavailable, readiness becomes `needs_review` to improve trust, but Q&A remains available if the KB is otherwise loaded.
