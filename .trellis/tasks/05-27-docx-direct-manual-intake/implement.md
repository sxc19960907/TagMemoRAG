# Implementation Plan

## Checklist

- [x] Add reusable `.docx` OpenXML-to-Markdown intake helper.
- [x] Convert `.docx` uploads in Manual Library write paths before validation/storage.
- [x] Preserve `source_format=docx` and original source marker metadata.
- [x] Keep `.doc` unsupported.
- [x] Update upload file accept hints and docs.
- [x] Add focused unit/static tests.
- [x] Run focused gates:
  - `python3 -m py_compile src/tagmemorag/docx_intake.py src/tagmemorag/manual_library.py tests/unit/test_manual_library.py tests/unit/test_manual_library_ui.py tests/unit/test_multiformat_real_knowledge.py tests/unit/test_documentation_handoffs.py`
  - `uv run pytest tests/unit/test_manual_library.py::test_upsert_docx_converts_to_markdown_and_preserves_source_format tests/unit/test_manual_library.py::test_malformed_docx_upload_fails_clearly tests/unit/test_manual_library.py::test_safe_source_path_rejects_traversal_and_unsupported_suffix tests/unit/test_manual_library_ui.py::test_manual_library_template_serves_dashboard_shell tests/unit/test_manual_library_ui.py::test_qa_page_static_asset_is_served tests/unit/test_multiformat_real_knowledge.py tests/unit/test_documentation_handoffs.py -q`
  - `git diff --check`

## Verification Notes

- Added `src/tagmemorag/docx_intake.py` and Manual Library conversion hooks for file and registry backends.
- Bulk import preview now normalizes `.docx` metadata to the stored `.md` source while preserving upload matching against the original `.docx` filename.
- `metadata_to_dict()` preserves generic lineage fields so sidecars retain `source_format=docx` and `remote_id`.
- Focused run: `13 passed` for docx/manual-library/UI/multiformat/documentation tests.
- Expanded run: `92 passed` across manual library, bulk import API, UI, multiformat, documentation, and parser suffix boundary tests.

## Rollback

Remove `docx_intake.py`, the Manual Library conversion hook, file-picker/doc updates, and related tests. Existing `.md`, `.txt`, and `.pdf` paths should remain unchanged.
