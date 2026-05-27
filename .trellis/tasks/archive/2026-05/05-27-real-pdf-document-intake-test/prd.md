# Real PDF and document intake test

## Goal

Test the current real-document intake boundary for text-based PDFs and Word-style documents before adding more importer behavior.

## User Value

When a user brings real manuals or business documents, we need to know which formats already work end to end, which formats fail clearly, and where the next implementation task should focus. The result should protect the existing stable RAG path while making the PDF/Doc support boundary honest.

## Confirmed Facts

- Native parsing supports `.md`, `.txt`, and text-based `.pdf`.
- LangChain parsing adds `.html`/`.htm`, not `.doc` or `.docx`.
- Real product-manual PDFs exist under `product_manuals/`.
- Multiformat fixture work currently converts remote `.docx` into Markdown before indexing; direct `.doc`/`.docx` intake is not advertised in README.
- Manual Library validation rejects unsupported source suffixes using the active parser provider suffix set.

## Requirements

- Run real PDF intake checks using the existing product manual PDFs and local/offline embedding path.
- Verify that supported PDF content produces searchable chunks and useful retrieval hits for representative questions.
- Verify the current Doc/Docx boundary explicitly:
  - direct `.doc`/`.docx` upload/source paths should fail clearly as unsupported;
  - converted Docx-to-Markdown fixture path should remain covered as the supported workaround.
- Capture results in a small retained report under `docs/` so the next task can choose between parser improvement, Docx conversion support, or UI/documentation changes.
- Preserve existing QA, manual-library, and parser behavior unless the tests reveal a small safe bug fix.

## Acceptance Criteria

- [x] Real product-manual PDF build/search check passes locally.
- [x] Direct `.doc` and `.docx` source validation is covered and fails with a clear unsupported-suffix error.
- [x] Existing Docx-to-Markdown multiformat fixture test remains green.
- [x] A report documents PDF result quality, Doc/Docx boundary, and recommended next implementation.
- [x] Focused unit/integration checks pass.
- [x] `git diff --check` passes.

## Verification Notes

- Exploratory `realmanuals.jsonl` eval over `product_manuals/` passed 10/10 cases with `recall@k=0.966667`, `MRR=0.833333`, and `hit@k=1.0`.
- `uv run pytest tests/unit/test_eval_runner.py::test_run_eval_real_product_manual_pdfs_pass_current_quality_bar tests/unit/test_manual_library.py::test_safe_source_path_rejects_traversal_and_unsupported_suffix tests/unit/test_langchain_ingestion.py tests/unit/test_multiformat_real_knowledge.py tests/unit/test_documentation_handoffs.py -q` passed with 11 tests.
- `python3 -m py_compile tests/unit/test_eval_runner.py tests/unit/test_manual_library.py tests/unit/test_langchain_ingestion.py tests/unit/test_multiformat_real_knowledge.py tests/unit/test_documentation_handoffs.py` passed.
- `git diff --check` passed.

## Spec Update Review

No `.trellis/spec/` update is needed yet. This task confirms and documents the current support boundary without changing parser, API, CLI, persistence, or runtime contracts. A future `.docx` importer or parser-warning summarization task should update specs when it changes supported suffixes or parser behavior.

## Out Of Scope

- Adding native `.doc`/`.docx` parsing in this task.
- OCR for scanned image-only PDFs.
- Live provider or remote download tests.
- GitHub push.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
