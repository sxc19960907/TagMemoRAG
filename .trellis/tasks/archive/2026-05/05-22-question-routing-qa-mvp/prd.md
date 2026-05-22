# Question routing QA MVP

## Goal

Move `/qa` from “ask a selected knowledge base” toward “describe the problem and let the system choose the right manual context.” Users should not choose a manual or KB; the backend should route automatically when possible or ask for clarification when not.

## Requirements

- Add a user-facing QA endpoint that accepts a question without a visible or required KB selector.
- Reuse existing `/answer` retrieval and answer-generation behavior after routing chooses a KB.
- Route among currently loaded, API-key-accessible KBs.
- Routing MVP behavior:
  - no accessible loaded KBs -> user-readable not-ready response
  - one accessible loaded KB -> answer with that KB
  - multiple accessible loaded KBs -> choose a KB when a lightweight lexical signal can identify one; otherwise return a clarification response with candidate KB labels
- Keep `/answer`, `/retrieve`, and `/admin/rag-workbench` unchanged for explicit admin/debug flows.
- Update `/qa` frontend to call the new user-facing endpoint with only the question and answer display options.

## Acceptance Criteria

- [x] `/qa/answer` accepts `{question}` and returns `route.kind="answered"` plus normal answer payload when routing succeeds.
- [x] `/qa/answer` returns `route.kind="clarification"` with candidate KBs when multiple KBs are plausible but no clear match is available.
- [x] `/qa/answer` returns a user-readable not-ready answer payload when no accessible KB is loaded.
- [x] The `/qa` page calls `/qa/answer` and no longer sends `kb_name` from the browser.
- [x] Existing `/answer` tests continue to pass.
- [x] Focused tests cover single-KB routing, ambiguous multi-KB routing, and the frontend asset contract.

## Notes

- Lightweight task: PRD-only is acceptable because the MVP is a thin API/UI layer over existing KB state and `/answer` implementation.
- Out of scope: LLM-based router, persistent sessions, user identity-to-tenant mapping, and full product catalog UI.
