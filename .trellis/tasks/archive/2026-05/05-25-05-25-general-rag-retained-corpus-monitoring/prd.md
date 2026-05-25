# General RAG retained corpus and monitoring program

## Goal

Run the next long-horizon general-purpose RAG stability program after the
same-page ordering default-on rollout. This program expands retained eval
coverage and adds post-default-on monitoring so future retrieval/ranking
changes are tested against broader, repeatable evidence.

## Requirements

- Maintain this as a parent program task with independently verifiable child
  tasks.
- Start with a retained corpus inventory: list existing eval suites,
  materialized corpora, retained reports, and coverage gaps.
- Expand retained coverage before making further ranking/retrieval behavior
  changes.
- Track post-default-on same-page ordering metrics across general-web,
  mixed-domain, multiformat, realmanuals, and any newly retained slices.
- Keep generated `.tmp` reports out of git; committed artifacts must be bounded
  summaries only.
- Preserve privacy constraints: no unbounded user/source content, provider
  response bodies, secrets, full candidate lists, or generated third-party
  document bodies in committed diagnostics.
- Each child must define acceptance criteria, run focused validation, update
  this parent log, commit, and archive when complete.

## Acceptance Criteria

- [ ] Parent program artifacts define roadmap, stability gates, and decision
      policy.
- [ ] First child task inventories retained corpus and report coverage.
- [ ] Each completed child leaves a clear recommendation for the next child.
- [ ] Release-readiness and reranking gates are not knowingly degraded by any
      child.
- [ ] The program stays active until the user asks to pause, finish, or change
      direction.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
