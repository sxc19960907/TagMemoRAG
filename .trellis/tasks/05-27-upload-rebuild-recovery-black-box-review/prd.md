# Upload Rebuild Recovery Black Box Review

## Goal

Verify and harden browser-first upload/rebuild recovery paths for trial operators.

## Requirements

- Treat Manual Library as the operator-facing recovery surface for upload and rebuild issues.
- Verify the browser flow for three trial states:
  - invalid upload metadata does not create a manual and shows an actionable error;
  - uploaded-but-not-rebuilt manuals remain visibly unsearchable with a rebuild next step;
  - rebuild failure or queued rebuild failure gives an explicit recovery route without implying Q&A is ready.
- Preserve the backend contract that failed rebuilds keep the previous served KB active.
- Avoid introducing new storage or queue semantics unless the browser flow cannot be made clear from existing signals.
- Keep diagnostics and recovery guidance safe: no raw document text, secrets, or stack traces in user-facing messages.

## Acceptance Criteria

- [ ] The child task documents the upload/rebuild recovery data flow and risk controls.
- [ ] Manual Library exposes clear browser-visible recovery guidance for pending or failed rebuild states.
- [ ] Existing upload -> rebuild -> Q&A success path remains covered.
- [ ] Invalid upload and pending rebuild states are covered by browser-oriented tests.
- [ ] If rebuild failure UI needs a wording adjustment, tests assert the new user-facing guidance.
- [ ] Focused validation passes before commit and archive.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
