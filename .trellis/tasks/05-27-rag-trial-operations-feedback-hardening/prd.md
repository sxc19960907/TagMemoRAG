# RAG Trial Operations And Feedback Hardening

## Goal

Move TagMemoRAG from a browser-first demo that passes local acceptance into a safer small-trial operating loop: real user feedback should be captured, triaged, promoted into regression checks when useful, and backed by repeatable health/pilot evidence.

## User Value

After a user starts trying the RAG system with real manuals, the project should make it easy to see what went wrong, decide what to fix next, and keep the system stable while iterating. The operator should not need to manually piece together feedback, readiness reports, and eval artifacts to understand trial health.

## Confirmed Facts

- The prior RAG UX completion program finished 7/7 child tasks and passed black-box browser acceptance.
- `pilot run --include-browser-qa` now produces a retained local trial report.
- QA feedback can link directly into Retrieval Quality.
- Browser QA readiness covers the core normal-user path.
- GitHub `master` has been pushed through commit `7630ba7`.

## Requirements

- Manage this as a parent task with independently verifiable child tasks.
- Keep trial operations browser-first where possible, but preserve CLI reports for automation and CI.
- Prioritize real-user trial risks: feedback triage, upload/rebuild recovery, eval promotion quality, auth/role clarity, and report discoverability.
- Keep live-provider/network-cost checks opt-in.
- Preserve stability with focused unit tests, readiness gates, and browser checks for affected areas.
- Archive completed child tasks and record journal progress.

## Child Task Roadmap

1. Trial handoff and operator dashboard review.
2. Feedback triage workflow hardening.
3. Upload/rebuild failure recovery black-box review.
4. Eval promotion quality review from real feedback.
5. Auth and role boundary trial review.
6. Trial report retention and CI handoff.
7. Final trial readiness review and GitHub/CI follow-up.

## Acceptance Criteria

- [ ] A trial operator can find the latest pilot/browser readiness evidence without searching terminal history.
- [ ] Not-helpful QA cases can be triaged into either dismissed feedback or eval-ready cases.
- [ ] Common upload/rebuild failure states show clear next actions and preserve existing served KBs.
- [ ] Trial-facing docs explain the exact browser entry points, commands, and expected report artifacts.
- [ ] Relevant local gates pass for every child task.
- [ ] Completed child tasks are archived and journaled.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
