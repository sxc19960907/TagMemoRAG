# QA Browser Regression Smoke

## Goal

Add a repeatable browser regression smoke for the user-facing QA flow: open page, ask, answer, sources, follow-ups, and feedback affordances.

## Confirmed Facts

- Browser integration tests live in `tests/integration/test_browser_admin_ui.py`.
- They are opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`, so adding coverage there will not slow default unit runs.
- Existing QA browser tests already cover answer submission, citation chip/source focus, feedback handoff, insufficient evidence, and follow-up context.
- The latest QA UX hardening added visible guidance surfaces that are not yet guarded by browser regression assertions:
  - Ask / Read / Verify flow guide.
  - Better empty-state guidance.
  - Loading progress card.
  - Source metadata that explains citation-to-source focus.
  - Follow-up explanatory copy.
  - Failure/recovery card with readiness link.

## Problem

The user-facing QA page has become the primary experience surface for RAG. Several important usability affordances are now only covered by unit/static string checks or manual browser inspection. If a later UI edit removes or hides those affordances, the existing browser tests may still pass because the core answer API flow remains intact.

## Requirements

- Extend the opt-in browser integration coverage for `/qa?kb_name=default`.
- Assert the QA page's current first-screen user guidance is visible in a real browser.
- Assert the loading/progress state appears during a real answer request.
- Assert a successful answer still exposes sources, citation focus, follow-up guidance, and feedback controls.
- Assert recovery guidance is visible for a not-ready or failed answer state.
- Keep the test deterministic, local, and compatible with the existing `TAGMEMORAG_RUN_BROWSER_UI=1` gate.
- Do not add external network dependencies or live model calls.
- Do not change QA product behavior except for narrow testability fixes if the browser test exposes a real defect.

## Acceptance Criteria

- [ ] Browser integration tests cover QA first-screen guidance.
- [ ] Browser integration tests cover QA loading/progress guidance during an answer request.
- [ ] Browser integration tests cover answer -> sources -> citation focus -> follow-up guidance -> feedback affordance.
- [ ] Browser integration tests cover not-ready/failure recovery guidance and readiness link visibility.
- [ ] Targeted browser integration test passes with `TAGMEMORAG_RUN_BROWSER_UI=1`.
- [ ] Related unit tests still pass.
- [ ] Task is committed, archived, journaled, and pushed.

## Out of Scope

- Adding a new browser automation framework.
- Making browser UI integration tests run by default.
- Changing retrieval ranking, answer generation, feedback persistence, or manual-library workflows.
- Adding visual screenshot snapshot testing.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
