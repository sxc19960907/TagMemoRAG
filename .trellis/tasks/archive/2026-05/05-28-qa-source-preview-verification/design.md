# QA Source Preview and Verification Design

## Boundary

This task spans retrieval evidence descriptors, the QA page source-card UI, and browser regression tests. It reuses the existing `/assets/{asset_id}` serving path for previewable page images and does not add a general raw-document download endpoint in this slice.

## Data Flow

1. Retrieval evidence already attaches `assets[]` when a visual asset resolver is configured and matching PDF page snapshots exist.
2. `/qa/answer` includes `retrieve.evidence` for the user page.
3. `qa_page.js` sanitizes evidence for session storage and renders source cards.
4. Source cards display a verification action area:
   - If a safe preview asset URL is present, show an action that opens it in a new tab/window.
   - If no asset is present, show a non-clickable fallback explaining that the cited snippet is the available verification context and include safe page/source labels.

## Safe Preview Contract

The QA page may keep these asset descriptor fields in session storage:

```json
{
  "asset_id": "asset:sha256:...",
  "type": "page_snapshot",
  "url": "/assets/asset%3Asha256...?kb_name=default",
  "mime_type": "image/png",
  "page_number": 3,
  "alt_text": "Page snapshot for cit_001"
}
```

Rules:

- Only relative `/assets/...` URLs are accepted by the QA page.
- Storage keys, checksums, local paths, blob keys, and raw diagnostics are discarded.
- The backend `/assets/{asset_id}` route remains responsible for auth, KB checks, and asset-store checks.
- Fallback cards never create a broken link; they explain that preview is unavailable and keep snippet/source/page information visible.

## UI

Each source card gets a compact verification row below provenance badges and above the cited snippet:

- Previewable asset: "Open source preview" action plus asset/page label.
- No asset: "Preview unavailable" note with page/source context.
- OCR card with preview asset: copy reinforces that OCR should be checked against the page image.

The UI stays operational and compact. It should not become a modal-heavy document viewer.

## Compatibility

- Evidence fields remain additive or frontend-only sanitized fields.
- Existing clients that ignore `assets[]` are unchanged.
- Existing QA source rendering still works for evidence without assets.

## Rollback

- If preview action UI causes layout or browser-test instability, keep asset sanitization and fall back to a text-only verification row.
