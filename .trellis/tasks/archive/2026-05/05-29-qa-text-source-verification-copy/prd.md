# Q&A text source verification copy

## Goal

Improve Q&A source-card copy for text and Markdown evidence so users understand that the cited snippet itself is the verification surface when no page/image preview is expected.

## Requirements

- Keep the existing preview-unavailable warnings for PDF/asset-generation failure cases.
- For normal text-like sources with no preview asset, show copy that frames the cited passage as directly verifiable.
- Update Chinese translation text.
- Update tests that assert source-card verification copy.
- Preserve citation focus and source-card behavior.

## Acceptance Criteria

- [x] Text/Markdown source cards no longer show generic "Preview unavailable" copy.
- [x] PDF/asset failure paths can still show preview-unavailable copy.
- [x] Browser/source-card tests pass.

## Verification Notes

- Normal text/Markdown source fallback now says the text source can be verified from the cited passage.
- Preview-unavailable copy remains for explicit asset-missing or asset-failure warnings.
- Chinese translations were updated.
- Verified with:
  - `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q -s`
