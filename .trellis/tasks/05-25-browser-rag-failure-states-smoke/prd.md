# Browser RAG failure states smoke

## Goal

Guard the main browser RAG experience when the user is not on the happy path: no loaded KB yet, upload metadata is invalid, and a newly uploaded manual still requires rebuild before QA can use it.

## Requirements

- Add browser-level smoke coverage for QA not-ready behavior in an empty local deployment.
- Add browser-level smoke coverage for upload form validation errors before a manual is written.
- Add browser-level smoke coverage for upload-without-rebuild state: manual appears in the library, but is not searchable and clearly requires rebuild.
- Keep the tests opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`.
- Reuse deterministic local hashing/noop settings; do not call external services.
- Do not commit generated runtime data, temp uploads, vectors, provider payloads, or secrets.

## Acceptance Criteria

- [ ] Empty `/qa?kb_name=default` question returns a clear not-ready message and no cited sources.
- [ ] Invalid upload metadata surfaces a visible validation error in the upload dialog and leaves the manual list empty.
- [ ] Upload without rebuild creates a visible manual row with `searchable=no`, `rebuild_required=required`, and dirty-state summary.
- [ ] Browser smoke fails on unexpected console errors.
- [ ] Focused unit/browser tests pass.
- [ ] Completed task is committed, archived, and recorded in the developer journal.

## Notes

- Lightweight task: this should primarily extend browser integration coverage. Production changes are only in scope if the smoke exposes a real user-visible defect.
