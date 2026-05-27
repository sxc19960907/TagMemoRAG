# QA Browser Regression Smoke Design

## Scope

Extend the existing opt-in Playwright integration suite in `tests/integration/test_browser_admin_ui.py`.

The preferred shape is to strengthen the existing QA browser helper assertions instead of creating a separate server/test harness:

- `_exercise_library_qa_user_flow` for first-screen, loading, answer, sources, citation focus, follow-up copy, and feedback affordance.
- `_exercise_rag_failure_states` for not-ready/failure recovery guidance.
- `_assert_qa_layout` for responsive layout guards as needed.

## Test Strategy

- Use the existing `TAGMEMORAG_RUN_BROWSER_UI=1` gate.
- Use local hashing embedder and noop answer provider.
- Seed manuals through existing demo/manual-library flows.
- Capture loading/progress by waiting for `#qa-answer` to contain the progress-card text immediately after submit.
- Avoid timing fragility by checking progress with a short best-effort assertion before waiting for `Answer ready.`
- Continue asserting no console/page errors.

## Contracts

- No production code changes are expected.
- If a production change is needed, it must be a narrow testability or accessibility improvement that preserves current UX.
- The test must stay local and deterministic.

## Rollback

Rollback is removing the added assertions or helper code from `tests/integration/test_browser_admin_ui.py`.
