# Implementation Plan

## Checklist

- [x] Add PDF quality summary contract and merge/serialization helpers.
- [x] Record per-PDF page counts in `_parse_pdf()` without changing chunk output.
- [x] Capture bounded parser extraction warning counts.
- [x] Merge PDF quality summaries in `build_kb()` and write `meta["pdf_quality"]`.
- [x] Return `last_rebuild.pdf_quality` from Manual Library diagnostics.
- [x] Add Manual Library diagnostics card and recommendation label.
- [x] Add focused parser/state/API/UI tests.
- [x] Run verification:
  - `python3 -m py_compile src/tagmemorag/parser.py src/tagmemorag/state.py src/tagmemorag/api_manual.py tests/unit/test_parser.py tests/unit/test_storage_state.py tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py`
  - `uv run pytest tests/unit/test_parser.py tests/unit/test_storage_state.py tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py -q`
  - `git diff --check`

## Risky Files / Rollback Points

- `src/tagmemorag/parser.py`: keep chunk output exactly the same; only add diagnostics.
- `src/tagmemorag/state.py`: meta addition must not leak raw text.
- `src/tagmemorag/web/static/manual_library.js`: static UI change only; no new build step.

## Done Criteria

- Existing focused tests remain green.
- New tests prove missing pages, OCR-created pages, and parser warnings are summarized safely.

## Verification Notes

- Focused verification passed: `7 passed`.
- Expanded related verification passed: `91 passed`.
- `git diff --check` passed before spec updates; rerun before finish.
