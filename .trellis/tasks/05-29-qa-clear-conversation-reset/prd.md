# Q&A clear conversation reset

## Goal

Make the user-facing Q&A page's clear action fully reset the visible conversation state so repeated demos, trials, and normal user sessions do not show stale answers, sources, or duplicate history items.

## Requirements

- Clear should remove all conversation history entries.
- Clear should reset the answer workspace to the empty/no-answer state.
- Clear should reset source cards to the empty/no-sources state.
- Clear should reset follow-up suggestions, feedback state, active citations, and submit-new state.
- Asking the same question after clear should create exactly one new history entry.
- Preserve normal Q&A ask, citation focus, and source display behavior.
- Add focused browser coverage for the clear-reset flow.

## Acceptance Criteria

- [x] After asking a question, the page shows answer, sources, and one history entry.
- [x] After clicking clear, the page shows no history entries, no answer, and no sources.
- [x] After asking the same question again, the page shows exactly one history entry.
- [x] Existing Q&A integration coverage still passes.

## Verification Notes

- Added a shared empty conversation renderer for the Q&A page.
- `Clear` now resets visible answer, source cards, follow-ups, feedback, copy state, active question text, submit-new state, status text, history, and session storage.
- Added browser integration coverage to `test_browser_manual_library_to_qa_user_flow`.
- Verified with:
  - `uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q -s`
