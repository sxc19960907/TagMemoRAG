# Trial Handoff And Operator Dashboard Review

## Goal

Create a current trial-operator handoff that explains where to start, which browser dashboards to use, where retained pilot/browser reports live, and how to route early user feedback.

## User Value

A trial operator should not need to read the whole README, old handoff notes, and multiple runbooks to begin a small local trial. They should have one concise, current guide that points to the browser surfaces and report artifacts that matter.

## Requirements

- Review existing trial/operator docs for stale or fragmented guidance.
- Add a current post-acceptance trial operator handoff document.
- Include the browser entry points, startup commands, local report commands, expected artifacts, and first feedback triage loop.
- Link the new handoff from the existing quick-start/handoff documentation.
- Do not change runtime behavior in this child task unless review exposes a blocker.

## Acceptance Criteria

- [ ] A trial operator can find one current handoff document for the post-acceptance RAG state.
- [ ] The handoff lists browser pages for Q&A, Manual Library, Retrieval Quality, Readiness, Eval Report, and People & Access.
- [ ] The handoff lists the retained `pilot run --include-browser-qa` command and expected report artifact.
- [ ] The handoff explains how to handle not-helpful feedback at a high level.
- [ ] Existing quick-start/handoff docs link to the new handoff.
- [ ] Focused documentation validation passes.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
