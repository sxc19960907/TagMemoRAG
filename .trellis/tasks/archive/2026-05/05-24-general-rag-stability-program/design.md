# Program Design

## Operating Model

This is a parent task. It should not usually own runtime implementation itself.
It owns:

- direction,
- stability policy,
- roadmap sequencing,
- child-task map,
- decision log.

Implementation happens in child tasks. A child task should be small enough to
verify and archive independently, but selected from the parent roadmap so the
work remains coherent.

## Stability Policy

Default posture:

- Do not change runtime retrieval/ranking behavior until the evaluation gate can
  prove the candidate is safe.
- Keep release readiness `passed`.
- Keep generated `.tmp` reports out of git.
- Keep diagnostic outputs bounded: no raw query text, raw snippets,
  `actual_top_k`, vectors, secrets, provider response bodies, or full candidate
  lists.
- Prefer additive scripts/docs/tests over behavior changes when uncertainty is
  high.

Runtime changes require:

- focused unit coverage,
- relevant real-data eval slices,
- release readiness check,
- reranking evaluation gate when ranking or evidence-usefulness is involved,
- explicit rollback path.

## Decision Loop

After each child task:

1. Record what changed.
2. Record validation evidence.
3. Classify result:
   - `ship`: safe improvement, continue to next planned child.
   - `hold`: useful evidence, no runtime change yet.
   - `pivot`: next child changes based on evidence.
   - `rollback`: revert or neutralize risky change before continuing.
4. Update `program-log.md`.
5. Create/start the next child task.

## Initial Roadmap

### P0. Baseline Batch Self-Check

Goal: run the current readiness, ranking-pressure, and reranking gate commands
as one retained self-check and record current status.

Why first: verifies the ground is stable before further experiments.

### P1. Gate Batch Runner

Goal: add a script that orchestrates general-web eval, ranking-pressure,
release-readiness, and reranking gate into one repeatable local batch.

Why second: reduces manual drift before experimenting.

### P2. Candidate Evidence-Usefulness Dry Run

Goal: prototype a candidate scoring report that observes answer-specific
signals without changing retrieval order.

Why third: gathers broader evidence before runtime behavior changes.

### P3. Candidate Evaluation Against Full Slices

Goal: run any candidate against general-web, mixed-domain, multi-format,
real-manual, context-quality, answer-quality, readiness, and reranking gate.

Why fourth: prevents overfitting GitHub cases.

### P4. Runtime Change Decision

Goal: decide whether to ship, reject, or keep observing a runtime
evidence-usefulness/reranking change.

Why last: only after gates and evidence are strong.

## Not In Scope

- Agentic behavior changes.
- Live provider dependence in default tests.
- Source-specific boosts for GitHub or one website.
- Changing Qdrant into authoritative final ranking without a separate PRD.
