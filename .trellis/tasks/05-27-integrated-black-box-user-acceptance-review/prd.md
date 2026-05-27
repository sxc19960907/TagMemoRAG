# Integrated Black Box User Acceptance Review

## Goal

Run the final browser-first acceptance review for the RAG user experience program and fix any issues that block a normal user from trying Q&A successfully.

## User Value

A normal user should be able to open the local demo in the browser, understand which knowledge base is active, ask useful questions, inspect evidence, switch language, submit feedback, and see a path from bad answers to quality review without knowing command-line details.

## Requirements

- Seed the deterministic demo KB before browser review.
- Use the in-app browser as the primary acceptance surface.
- Treat this as black-box review: judge visible behavior from the browser first; only inspect code when a defect needs fixing.
- Verify at least three realistic Q&A questions from the user's perspective.
- Verify evidence/citation visibility and a clear recovery/feedback path.
- Verify language switching remains usable.
- Verify the feedback-to-Retrieval-Quality handoff works from the page.
- Run the retained pilot/browser gates after review.
- Do not push to GitHub.

## Acceptance Criteria

- [ ] Demo KB seeds successfully.
- [ ] Browser QA page opens with clear active KB and usable first-screen guidance.
- [ ] At least three realistic questions produce useful grounded answers or clear recovery state.
- [ ] Citations/source evidence can be inspected from the answer page.
- [ ] English/Chinese language switching works on the QA page.
- [ ] Not-helpful feedback creates a visible Retrieval Quality handoff and auto-selects the feedback record.
- [ ] Retained pilot report with `--include-browser-qa` passes.
- [ ] Any blocking user-facing defects found during black-box review are fixed or explicitly documented as non-blocking.

## Notes

- This task may be documentation/report-only if the black-box review finds no code defects.
- Keep the review evidence under `.tmp/` and summarize retained artifacts in task docs.
