# RAG onboarding readiness guide

## Goal

Make `/admin/rag-readiness` a polished, user-friendly onboarding guide for getting a knowledge base from "not ready" to "ready for browser Q&A".

The page should help a non-developer understand the current state, the next action, and the expected path to a usable RAG experience without reading logs or running CLI commands.

## Confirmed Facts

- `/admin/rag-readiness` and `/admin/rag-readiness/summary` already exist.
- The summary API already provides overall status, cards, actions, primary action, and recommendations.
- The current page renders these signals, but visually reads like a diagnostics panel rather than an onboarding guide.
- The user explicitly wants a beautiful, easy-to-understand guide.
- The direct user journey is browser-first; CLI-only validation is insufficient.

## Requirements

- Preserve the existing readiness API contract unless a small additive field is clearly needed.
- Redesign the readiness page around an onboarding flow:
  - clear hero with current readiness state and primary next action
  - simple progress/stepper explaining the path: load KB, index manuals, review retrieval quality, start Q&A
  - concise readiness cards with human-readable metrics
  - recommendations that look like actionable tasks, not raw diagnostics
  - quick links to Q&A, Manual Library, Workbench, Retrieval Quality, and Eval Report
- Keep the page visually consistent with the existing admin UI while making it more attractive and easier to scan.
- Support existing Chinese/English language switching for new visible text.
- Avoid exposing unsafe internals such as local paths, storage keys, blob keys, checksums, node ids, raw manifest rows, or debug identifiers in the onboarding page.
- Add browser coverage for the improved readiness guide in at least a not-ready and/or ready scenario.
- Keep existing Manual Library and QA page behavior stable.

## Acceptance Criteria

- [ ] The readiness page first viewport shows a clear status, summary, primary action, and onboarding progress.
- [ ] Cards and recommendations are easy to understand without raw diagnostic jargon.
- [ ] Navigation/action links point to the selected `kb_name`.
- [ ] New UI text is covered by the i18n dictionary for Chinese/English switching.
- [ ] Browser integration verifies the guide renders and guides the user in a real page flow.
- [ ] Existing focused browser QA/readiness-adjacent tests still pass.
- [ ] Broader unit/e2e checks pass or any skipped real-provider checks are explicitly explained.

## Out of Scope

- Building a full configuration wizard for API keys or external providers.
- Changing the retrieval, rebuild, or answer generation algorithms.
- Adding account-level onboarding state persistence.
- Pushing to GitHub.
