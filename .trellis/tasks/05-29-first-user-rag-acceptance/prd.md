# First user RAG acceptance

## Goal

Verify and harden the first-user RAG experience from public project entry points through the browser Q&A flow, so a normal user can understand how to start, upload real documents, ask questions, inspect sources, and recover from common confusion without relying on command-line-only knowledge.

## User Value

A first-time evaluator should be able to open the docs/README, run the documented local demo, use browser pages, upload real documents, ask cited questions, switch language, and understand source verification status. If the path fails, the product should reveal actionable next steps rather than exposing internal implementation details.

## Confirmed Facts

- README points to the public docs site, repository, current release, browser quick start, local demo command, local page URLs, and supported document boundaries.
- `docs/browser-rag-quick-start.md` documents the browser-first flow, Q&A upload path, Manual Library upload path, language switching, and opt-in browser smoke commands.
- The public static documentation site lives under `site/` and is covered by `tests/unit/test_public_site.py`.
- Existing browser tests cover seeded Q&A, QA-page upload/index/answer, multiformat TXT/PDF/DOCX upload and Q&A, PDF source preview, scanned-PDF OCR when local tools are available, language switching, source-card verification, conversation reset, insufficient-evidence refusal, and follow-up context.
- Direct `.docx` intake is supported by extracting OpenXML text and materializing Markdown while preserving original-source metadata. Legacy `.doc` is not currently in scope.
- Scanned PDFs require OCR configuration and local OCR tooling; without OCR, image-only pages may not produce searchable text.

## Requirements

- Run a black-box acceptance pass using the documented browser-first entry points and record the result.
- Verify the public docs/README/quick-start path is internally consistent with the current browser UI labels and supported document formats.
- Verify real browser Q&A flow covers first-run empty KB guidance, upload/index, ask-ready transition, cited source cards, language switching, and source verification language.
- Verify multiformat browser flow still works for TXT, text PDF, and DOCX with no storage/blob key leakage in the UI.
- Verify OCR/scanned-PDF user guidance is either tested when local tools are present or clearly reported as skipped with the reason.
- Fix any small UX/docs/test gaps found during the acceptance pass within this task.
- Preserve existing stable QA behavior: answer generation, citations, source-card focus, clear-history reset, and language switching.

## Out Of Scope

- Adding legacy binary `.doc` support.
- Changing OCR provider architecture or enabling OCR by default.
- Production deployment hardening, backup/restore policy, or multi-tenant rollout controls.
- Replacing the current public docs site framework.
- Introducing external model/provider requirements for the default local demo.

## Acceptance Criteria

- [x] A documented black-box acceptance pass is saved under the task directory.
- [x] Public docs/README/quick-start references match the current UI and support boundaries.
- [x] Browser Q&A first-user flow passes using real upload/index/answer behavior.
- [x] Browser multiformat TXT/PDF/DOCX flow passes or any failure is fixed and covered.
- [x] OCR/scanned-PDF path is validated when tools/sample exist, or the skip reason is recorded.
- [x] Relevant focused tests and quality checks pass.
- [ ] Work is committed, pushed, CI passes, and the task is archived.

## Verification

- `uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer -q -s`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q -s`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa -q -s`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa -q -s`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
