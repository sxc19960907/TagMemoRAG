# QA context transparency

## Goal

Make `/qa` follow-up context visible and correctable so users understand when the assistant is continuing a prior topic.

## Requirements

- Extend `/qa/answer` responses with a small, non-debug context metadata object.
- The metadata must say whether context was applied and provide a bounded display summary of the prior turn.
- Do not expose the full effective retrieval question, plan id, build id, or trace id on the user page.
- Add a user-facing "new question" override so a short message can be sent without conversation context.
- Show a compact notice when an answer used prior context.
- Mark local history items that used context.
- Keep existing short-term session memory, history restore, source/citation, feedback, and follow-up flows working.

## Acceptance Criteria

- [x] API tests cover `context.applied=false` for single-turn requests and `context.applied=true` for contextual follow-ups.
- [x] The `/qa` page sends `conversation_context: []` when the user chooses the new-question override.
- [x] The `/qa` page renders a context notice for context-applied answers.
- [x] History entries indicate when a turn used prior context.
- [x] Focused UI/API tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
