# GitHub ranking pressure root cause

## Goal

Diagnose the two remaining general-web GitHub Hello World ranking-pressure
cases and decide whether they justify a runtime ranking change, fixture
refinement, or backlog-only follow-up.

The task should preserve the current general-purpose RAG release posture:
release readiness is already `passed`, and ranking pressure is non-blocking
visibility. This task exists to avoid making a broad ranking change from a
thin signal.

## Confirmed Facts

- The retained general-web ranking-pressure report identifies two cases:
  `github-hello-world-repository` and `github-hello-world-pull-request`.
- Both cases are `hit@k=1.0`; the weakness is rank/MRR, not missing recall.
- Both cases come from the same real public GitHub Hello World document.
- The current release-readiness status remains `passed`; ranking pressure is
  surfaced as a non-blocking next-step hint.
- Runtime retrieval should not change unless the diagnosis shows a general,
  low-risk signal that preserves existing benchmark quality.

## Requirements

- Inspect the existing ranking-pressure report and the underlying general-web
  eval report for the two GitHub cases.
- Classify each case as one of:
  - fixture/evidence-label issue,
  - parser/chunking issue,
  - runtime ranking issue,
  - acceptable overview-first behavior with backlog-only follow-up.
- Record the root-cause conclusion in a task artifact.
- If a runtime ranking change is not justified, explicitly say so and keep
  source code unchanged.
- Preserve privacy and diagnostic bounds: do not commit raw fetched web
  content, raw full top-k result payloads, vectors, or `.tmp/` outputs.

## Acceptance Criteria

- [ ] A diagnosis artifact explains why the two GitHub cases are under-ranked.
- [ ] The diagnosis states whether the next step should change runtime ranking,
      refine eval labels, or remain backlog-only.
- [ ] Reproducible validation commands are recorded.
- [ ] No runtime behavior changes are made unless explicitly justified by the
      diagnosis and validated against current release-readiness slices.
- [ ] The task is archived after the decision is recorded.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
