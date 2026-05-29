# Implementation Plan

## Steps

- [x] Read relevant Trellis specs and current docs/test surfaces.
- [x] Add/extend real product PDF browser black-box coverage to at least three product categories.
- [x] Add production release/deployment checklist doc.
- [x] Revise `site/index.html` and `site/styles.css` into a stronger official docs hub.
- [x] Update public-site and documentation tests.
- [x] Run focused docs tests:
  - `uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
- [x] Run focused browser real-product test when prerequisites exist:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_real_product_pdf_source_preview_user_flow -q -s`
- [x] Run final quality gate:
  - `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- [x] Mark PRD acceptance criteria and record verification notes.
- [ ] Commit, archive, record journal, push, and watch CI.

## Risk Notes

- Real PDF content can be noisy; assertions should target stable source routing and category separation rather than brittle exact answer phrasing.
- Optional PyMuPDF/fitz and local real PDFs are required for source-preview browser coverage.
- Public docs must not expose internal storage keys, blob keys, checksums, raw secrets, or local absolute paths.
