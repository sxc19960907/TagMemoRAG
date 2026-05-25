# Browser navigation from library to QA

## Goal

Make the normal browser RAG path discoverable from the UI: after users manage manuals and rebuild the library, they should be able to enter the user-facing QA page from Manual Library without knowing or typing the `/qa` URL.

## Requirements

- Add a visible Manual Library navigation link to the user-facing QA page for the selected KB.
- Preserve existing Manual Library controls and layout.
- The link must include the current `kb_name` query parameter.
- Update browser smoke coverage so at least one upload/rebuild-to-QA path clicks the UI link instead of manually navigating to `/qa`.
- Keep browser tests opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`.

## Acceptance Criteria

- [ ] Manual Library shell exposes a stable `id="manual-library-qa-link"` link.
- [ ] The link points to `/qa?kb_name=<current kb>`.
- [ ] Browser upload/rebuild QA smoke clicks the Manual Library QA link and successfully asks a question on the QA page.
- [ ] Focused unit/browser tests pass.
- [ ] Completed task is committed, archived, and recorded in the developer journal.

## Notes

- Lightweight UI task: no backend behavior changes are intended.
