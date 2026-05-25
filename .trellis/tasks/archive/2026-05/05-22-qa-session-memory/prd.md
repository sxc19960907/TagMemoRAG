# QA session memory

## Goal

Upgrade `/qa` short-term memory from in-page state to tab-session state so refreshes do not lose recent conversation context.

## Requirements

- Use browser `sessionStorage`, not backend persistence or `localStorage`.
- Save only bounded user-facing turn data needed to restore the current tab session.
- Do not save or surface debug identifiers such as `plan_id`, `build_id`, or `trace_id`.
- Restore recent turns and the active turn after page reload.
- Preserve the existing "Clear" button behavior and make it clear stored memory is removed.
- Keep existing follow-up context behavior working from restored turns.
- Tolerate unavailable or corrupted storage without breaking the page.

## Acceptance Criteria

- [x] `qa_page.js` loads and saves recent turns through `sessionStorage`.
- [x] Pending turns are not stored as pending across reload; stale pending turns become error/unavailable.
- [x] Clearing history also clears session storage.
- [x] Restoring a reloaded answered turn restores answer, sources, follow-ups, and feedback state.
- [x] Focused UI/API tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
