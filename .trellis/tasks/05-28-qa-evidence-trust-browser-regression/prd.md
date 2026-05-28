# QA evidence trust and browser regression

## Goal

Finish the next user-facing RAG slice by improving evidence explainability on the QA page and locking the core browser experience with black-box regression coverage. Users should be able to see where an answer came from, understand whether a source was converted from DOCX/PDF/OCR, inspect cited passages, and get useful recovery guidance when evidence is insufficient.

## Confirmed Facts

- QA already renders answer bubbles, citation chips, Sources cards, source expansion, feedback, follow-ups, and conversation history.
- `/qa/answer` includes `retrieve.evidence` when requested; evidence currently carries citation ids, source file, page range, section path, text, score/confidence, reason, and assets.
- Managed DOCX intake rewrites `.docx` to a stored `.md` source while retaining `source_format=docx` and `remote_id=<original .docx source_file>` in metadata.
- PDF/OCR chunks already carry page metadata and OCR lineage in chunk metadata.
- Current QA Sources cards do not clearly show original DOCX provenance, page range, OCR lineage, or human-readable evidence strength.
- Existing browser integration covers upload/rebuild/QA for Markdown, TXT, text PDF, DOCX, scanned PDF OCR, refusal states, follow-up context, feedback, and layout.

## Requirements

- Surface safe evidence provenance in `/retrieve`/`/qa/answer` payloads without exposing raw document bodies, vectors, local paths, storage keys, or secrets.
- Show source provenance on QA Sources cards:
  - original DOCX source when the indexed file is converted Markdown,
  - PDF page range when available,
  - OCR-derived marker when evidence came from OCR chunks,
  - confidence/strength label from evidence confidence.
- Keep citation chips clickable and ensure the focused source is visually and programmatically identifiable.
- Improve evidence-insufficient/refusal UX with actionable guidance already available from the QA page.
- Build a browser regression that behaves like a user: upload documents, ask questions, inspect source cards/citations, test refusal guidance, feedback link, conversation history, language switch, and mobile layout.
- Keep QA page free of low-level debug fields such as `node_id`, raw `source_k`, vector ids, storage paths, or raw diagnostics.
- Preserve existing APIs for clients; new fields must be additive and backward compatible.

## Acceptance Criteria

- [x] `retrieve.evidence[]` includes bounded provenance fields for source format, original source, page range, OCR status, and confidence where available.
- [x] QA Sources cards display original DOCX provenance, page/page range for PDFs, OCR marker for OCR chunks, and a readable evidence strength indicator.
- [x] Citation chip click focuses the matching source card and the active card is detectable in browser tests.
- [x] Evidence-insufficient/refusal state gives clear recovery actions without raw debug metadata.
- [x] A browser black-box regression covers upload → rebuild → QA → citation focus → source inspection → feedback review link → history restore → language switch → mobile layout.
- [x] Existing browser upload, multiformat, OCR, refusal, follow-up, and feedback flows remain green.
- [x] Focused unit/UI tests and CI-equivalent tests pass.

## Verification

- `uv run pytest tests/unit/test_retrieval.py tests/unit/test_manual_library_ui.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer tests/integration/test_browser_admin_ui.py::test_browser_qa_insufficient_evidence_refusal tests/integration/test_browser_admin_ui.py::test_browser_qa_followup_uses_conversation_context -q`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
