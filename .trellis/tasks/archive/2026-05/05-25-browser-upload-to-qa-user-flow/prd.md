# Browser upload to QA user flow

## Goal

Guard the normal-user RAG path from an empty local browser session: upload a manual through the Manual Library UI, trigger rebuild from the same UI action, then ask the QA page a question and see a cited grounded answer from the uploaded manual.

## Requirements

- Add browser-level smoke coverage for uploading a Markdown manual through `/admin/manual-library`.
- The smoke must use the real upload form, including file input, metadata fields, and `trigger_rebuild`.
- The smoke must wait for rebuild completion through the UI state, then verify the uploaded manual is searchable, has chunks, and has no pending rebuild.
- The smoke must then open `/qa?kb_name=default`, submit a question, and verify the visible answer and source list cite the uploaded manual.
- Keep the browser smoke opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`.
- Use deterministic local hashing/noop answer configuration; no network providers, Qdrant, or external services.
- Do not commit generated runtime data, uploaded temp files, vectors, provider payloads, or secrets.

## Acceptance Criteria

- [ ] New browser integration path starts from an empty temporary KB and performs upload through the UI.
- [ ] Rebuild completion is observed from the UI before asking QA.
- [ ] Manual Library row shows the uploaded manual as searchable with non-zero chunks and clear rebuild state.
- [ ] QA page returns an answer containing the uploaded manual's service-mode guidance.
- [ ] QA source list includes the uploaded manual source file.
- [ ] Browser smoke fails on unexpected console errors.
- [ ] Focused unit/browser tests pass.
- [ ] Completed task is committed, archived, and recorded in the developer journal.

## Notes

- Lightweight task: reuse the existing browser integration harness and UI/API behavior rather than changing production code unless the smoke exposes a real defect.
