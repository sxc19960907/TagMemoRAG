# General RAG stability program

## Goal

Run a long-horizon, result-driven program to improve TagMemoRAG as a
general-purpose RAG system while preserving system stability.

This program replaces ad hoc short task chains with a parent/child task tree.
The parent owns direction, stability gates, and decision policy. Each child
task owns one independently verifiable deliverable and is selected based on the
previous task's evidence.

## User Intent

- Continue working for a long horizon, not just a few small tasks.
- Make a plan, then keep executing it.
- Use each task's result to decide the next task.
- Preserve system stability and avoid accidental functional divergence.
- Stay aligned with the general-purpose RAG direction, not agentic-specific
  behavior.

## Current Baseline

- Release readiness is `passed`.
- General-web retrieval baseline:
  - `hit@k=1.0`
  - `recall_at_k=0.971429`
  - `MRR=0.773810`
- General-web ranking pressure is visible but non-blocking:
  - `ranking_pressure_count=2`
  - `highest_pressure_rank_count=5`
- GitHub Hello World pressure cases were diagnosed as real low-MRR cases, but
  too thin to justify immediate runtime ranking changes.
- A reranking evaluation gate now exists and is documented.

## Requirements

- Maintain a parent program task with child tasks for concrete work.
- Before runtime behavior changes, run or define gates that protect current
  release readiness.
- Prefer diagnostics, report comparison, and bounded evaluation automation
  before changing ranking behavior.
- For each child task:
  - define acceptance criteria,
  - run focused validation,
  - record bounded evidence,
  - commit,
  - archive when complete,
  - update this parent program's progress/decision log.
- Do not commit generated `.tmp` reports, raw queries, raw snippets, vectors,
  provider secrets, full candidate lists, or fetched third-party document bodies.

## Acceptance Criteria

- [ ] Parent program artifacts define roadmap, stability gates, and decision
      policy.
- [ ] At least one child task is created and started from the roadmap.
- [ ] Each completed child leaves a clear recommendation for the next child.
- [ ] Release-readiness status must not be knowingly degraded by any child.
- [ ] The program remains active until the user asks to pause, finish, or
      change direction.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
