# Browser QA followup context smoke

## Goal

Guard the QA browser page's normal multi-turn experience: after an initial grounded answer, a short follow-up should automatically carry conversation context and visibly tell the user it is continuing from the previous question.

## Requirements

- Add browser-level smoke coverage for QA follow-up context from the real page.
- The smoke must start from a rebuilt local KB and ask an initial grounded question.
- The smoke must submit a short follow-up that the frontend classifies as context-dependent.
- The smoke must verify the backend response context is reflected in the UI via the "Continuing from earlier" notice.
- The smoke must verify the follow-up still returns a grounded answer with cited manual evidence.
- Keep browser coverage opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`.
- Use deterministic local hashing/noop configuration; no external services.

## Acceptance Criteria

- [ ] Browser smoke uploads/rebuilds a local manual, asks an initial QA question, then asks a follow-up.
- [ ] The follow-up answer displays the conversation-context notice with the previous question.
- [ ] The follow-up answer remains grounded and cites the uploaded manual.
- [ ] Browser smoke fails on unexpected console errors.
- [ ] Focused unit/browser tests pass.
- [ ] Completed task is committed, archived, and recorded in the developer journal.

## Notes

- Lightweight task: existing backend unit coverage already verifies route context; this task adds browser-level coverage for the UI behavior.
