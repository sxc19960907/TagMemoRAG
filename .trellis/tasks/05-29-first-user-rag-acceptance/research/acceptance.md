# First User RAG Acceptance Pass - 2026-05-29

## Scope

Black-box acceptance and consistency pass for the first-user RAG path:

- README and public docs entry points.
- Browser quick start.
- Q&A first-run upload/index/ask path.
- Manual Library multiformat upload path.
- TXT, text PDF, DOCX, and scanned-PDF OCR browser flows.
- Language switching and source verification surfaces.

## Evidence Reviewed

- `README.md`
- `docs/browser-rag-quick-start.md`
- `site/index.html`
- `src/tagmemorag/web/templates/qa_page.html`
- `src/tagmemorag/web/static/qa_page.js`
- `src/tagmemorag/web/static/i18n.js`
- `tests/integration/test_browser_admin_ui.py`
- `tests/unit/test_public_site.py`
- `tests/unit/test_documentation_handoffs.py`

## Test Results

| Check | Result | Notes |
| --- | --- | --- |
| Public docs and handoff checks | PASS | `5 passed` |
| Q&A first-run upload/index/answer browser flow | PASS | Real browser test over uploaded Markdown manual |
| Multiformat TXT/PDF/DOCX browser flow | PASS | Real browser test verifies source cards, language switching, and no safe-link leakage |
| Scanned-PDF OCR browser flow | PASS | `pdftoppm`, `tesseract`, and `.tmp/ocr-samples/scanned-coffee-manual.pdf` were present locally |

## Findings

### Fixed

- `docs/browser-rag-quick-start.md` used the stale button label **Add and index** for the Q&A upload form. The live UI label is **Upload and index**, so the quick start now matches the browser page.

### Confirmed Working

- README and quick start describe `.md`, `.txt`, text-based `.pdf`, and readable `.docx` support consistently with the current browser upload surface.
- Q&A first-run empty-KB state guides the user to upload, index, and then ask.
- Upload from Q&A transitions to ask-ready behavior.
- Source cards show cited passages and verification copy without exposing `storage_key`, `blob_key`, checksums, `node_id`, or `anchor_key`.
- DOCX source cards preserve the original `.docx` provenance while indexing materialized Markdown.
- OCR scanned-PDF flow works on this machine with local OCR tooling installed and the generated scanned sample present.

## Residual Risk

- OCR remains environment-dependent. The browser test skips when required system tools or the scanned sample are absent.
- The public docs site is intentionally static and concise; deeper operator detail remains in Markdown docs.
