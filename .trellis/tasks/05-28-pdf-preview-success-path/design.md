# PDF preview success path and config guidance design

## Scope

This task validates and smooths the page-preview happy path. It builds on the existing asset pipeline, `/assets/{asset_id}` route, QA source verification UI, and source preview readiness diagnostics.

## Data flow

1. Manual Library rebuild reads a PDF.
2. `extract_pdf_page_snapshots()` creates `page_snapshot` assets when `assets.enabled=true`, `assets.pdf_page_snapshots_enabled=true`, and PyMuPDF is importable.
3. Retrieval attaches safe asset descriptors to evidence based on document/page lineage.
4. QA source cards render `Open source preview` for safe `/assets/...` URLs.
5. The browser opens the image response from `/assets/{asset_id}`.

## Guidance contract

Diagnostics and readiness may expose safe config guidance:

- `assets.enabled=true`
- `assets.pdf_page_snapshots_enabled=true`
- renderer label: `pymupdf`

They must not expose asset `storage_key`, checksum, local paths, raw manifest records, or local dependency paths.

## Compatibility

Normal CI must not require PyMuPDF. Success-path tests should skip when the optional renderer is absent or mock the renderer boundary. Browser validation can run opportunistically in the developer environment when dependencies exist.
