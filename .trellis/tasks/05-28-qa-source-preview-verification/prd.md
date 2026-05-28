# QA source preview and original evidence verification

## Goal

Complete the QA trust loop by letting a normal browser user move from an answer citation to verifiable original evidence. After the previous provenance work, the user can see which file/page/chunk was cited; this task adds a safe preview/action path so the user can inspect the cited source context without using the admin workbench or command line.

## Confirmed Facts

- QA source cards already render citation focus, source snippets, evidence strength, page ranges, DOCX conversion provenance, OCR labels, source expansion, feedback, history restore, language switching, and mobile layout.
- `/retrieve` evidence can include visual `assets[]` descriptors with safe `/assets/{asset_id}?kb_name=...` URLs for PDF page snapshots when asset extraction is enabled and matching assets exist.
- `GET /assets/{asset_id}` already serves ready document assets behind `search` scope and validates KB ownership.
- Managed manual uploads are stored in the manual registry/blob store when the SQLite registry is enabled. Existing list/diagnostics APIs expose safe manual metadata, not raw local paths.
- User-facing QA must not expose local absolute paths, storage keys, node ids, vectors, raw top results, plan/build ids, or tuning controls.
- Browser tests already create TXT/PDF/DOCX uploads and exercise QA in a real browser.

## Requirements

- Add user-facing source verification controls to QA source cards:
  - open an available PDF/page snapshot evidence asset when `assets[]` contains a safe URL,
  - show a clear fallback when the original page/file preview is not available,
  - keep the existing source snippet and citation focus behavior intact.
- Add safe original-source context to evidence where needed for preview labels, without exposing storage keys or local paths.
- For DOCX-derived evidence, keep the original DOCX provenance visible and make clear when the indexed Markdown is the searchable representation.
- For OCR-derived evidence, make clear that preview should be checked against the scan/page image when an asset is available.
- Preserve auth and KB boundaries for every preview/open action.
- Keep the QA page usable on mobile and after session history restore.
- Extend browser regression so a user can ask a question, click a citation, inspect/open the preview action, restore history, and still see verification controls.

## Acceptance Criteria

- [x] QA source cards render a stable verification action area for cited evidence.
- [x] When evidence has ready visual assets, the QA card offers an Open/Preview source action using the safe `/assets/{asset_id}` URL and does not expose storage keys.
- [x] When evidence has no previewable asset, the QA card shows a concise unavailable state with source/page/provenance context rather than a broken link.
- [x] DOCX and OCR source cards keep their provenance labels alongside verification controls.
- [x] Session history sanitization preserves only safe preview descriptors needed to restore the source card.
- [x] Browser regression covers upload/rebuild/QA/citation focus/source verification action/history restore/mobile layout.
- [x] Existing QA upload, multiformat, refusal, follow-up, feedback, provenance, and CI/eval gates remain green.

## Verification

- `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_retrieval.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer tests/integration/test_browser_admin_ui.py::test_browser_qa_insufficient_evidence_refusal tests/integration/test_browser_admin_ui.py::test_browser_qa_followup_uses_conversation_context -q`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`

## Out of Scope

- Full embedded PDF viewer, arbitrary byte-range PDF streaming, or rendering DOCX in the browser.
- New document parser/OCR logic.
- Exposing raw registry blob keys, local file paths, or admin diagnostics on the QA page.
