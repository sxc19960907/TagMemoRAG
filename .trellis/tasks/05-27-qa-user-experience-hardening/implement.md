# QA User Experience Hardening Implementation Plan

1. Read applicable Trellis backend/frontend-adjacent specs before editing.
2. Run a black-box browser baseline on `/qa?kb_name=default` and note visible friction.
3. Update QA template with a compact guidance strip and any static recovery affordances.
4. Update QA JS rendering for clearer empty/loading/success/error/source/follow-up states.
5. Add CSS for new QA guidance and recovery surfaces, keeping the existing three-pane layout.
6. Add i18n strings for all new visible text.
7. Update unit/static tests for new shell/static strings.
8. Run syntax checks:
   - `node --check src/tagmemorag/web/static/qa_page.js`
   - `node --check src/tagmemorag/web/static/i18n.js`
9. Run targeted tests:
   - `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py -q`
10. Run browser smoke against a local server:
    - open `/qa?kb_name=default`
    - ask a fixture question
    - verify answer, source count, follow-up, feedback, and readiness recovery affordances
11. Run `git diff --check`.
12. Commit implementation, archive task, record journal, and push.

## Risk Notes

- Avoid broad visual redesign; the page was recently improved and should remain recognizable.
- Do not make QA depend on admin-only readiness summary calls.
- Keep feedback and answer API payloads unchanged.
