# Test Tier And Quality Gate Documentation

## Goal

Document the local test tiers and quality gates for browser-first RAG development so future work can choose the right verification commands consistently.

## User Value

Future RAG UX work should not depend on memory or chat history to decide whether the system is stable. Developers and operators should have one clear place that explains which checks are fast, which checks exercise the real browser QA path, which checks are release-oriented, and which checks require live providers.

## Confirmed Facts

- `readiness smoke` covers deterministic backend composition.
- `readiness browser-qa` now covers the focused normal-user browser QA path, with `--full` for the complete browser UI suite.
- Existing docs mention individual commands across README, system-test-plan, pre-merge closure notes, and deployment runbooks, but not a durable tiered gate model.
- Browser UI tests are opt-in because they require Playwright/Chromium.
- Network-dependent GitHub push remains deferred by user request.

## Requirements

- Add a durable quality-gates document that explains test tiers by purpose, when to run them, and exact commands.
- Cover at least: fast local development checks, RAG backend composition, browser QA readiness, release/local regression, eval, and live-provider/deployment checks.
- Explain which gates are required for normal browser-first QA changes.
- Link the new document from README and the system test plan.
- Keep commands aligned with current CLI names and recent browser QA readiness gate.

## Acceptance Criteria

- [ ] A new doc explains the tiered gate model with exact commands.
- [ ] README points readers from readiness checks to the full gate matrix.
- [ ] `docs/system-test-plan.md` references the tiered quality-gates document.
- [ ] The parent program implementation checklist reflects completed child tasks 1-3.
- [ ] Markdown/docs checks pass for the changed docs where practical.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
