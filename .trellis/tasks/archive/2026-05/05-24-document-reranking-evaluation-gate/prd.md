# Document reranking evaluation gate

## Goal

Document how to use the offline reranking evaluation gate before shipping
future general-purpose reranking or evidence-usefulness changes.

The runner exists in code now; this task makes it discoverable from the normal
eval workflow docs without changing runtime behavior.

## Requirements

- Add README guidance near the general-web / retrieval-tuning eval section.
- Add workflow guidance to `docs/eval-baseline-workflow.md`.
- Include the baseline/candidate report inputs, expected exit-code behavior, and
  privacy boundary.
- Keep the documentation clear that this is a pre-ship gate for candidate
  ranking changes, not part of default fixture-only CI.

## Acceptance Criteria

- [ ] README includes a runnable `scripts/reranking_eval_gate.py` example.
- [ ] Eval workflow docs explain when to run the gate and what failure means.
- [ ] Docs mention bounded output and that `.tmp` reports should not be
      committed.
- [ ] No runtime code changes are made.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
