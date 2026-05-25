# Program Design

## Operating Model

This is a parent program. It owns direction, evidence policy, roadmap
sequencing, and the decision log. Implementation and concrete evidence work
happen in child tasks that can be committed and archived independently.

## Stability Policy

- Treat same-page ordering as default-on baseline behavior.
- Do not broaden ranking/retrieval heuristics until retained coverage proves
  current behavior is stable across more slices.
- Keep release readiness and reranking gate checks passing.
- Keep generated `.tmp` reports uncommitted.
- Commit only bounded summaries: aggregate metrics, statuses, paths, decisions,
  and rollback notes.
- Preserve config rollback for default-on behavior.

## Decision Loop

After each child:

1. Record what changed or what evidence was gathered.
2. Record validation commands and bounded results.
3. Classify result as `ship`, `hold`, `pivot`, or `rollback`.
4. Update `program-log.md`.
5. Choose the next child from the roadmap based on evidence.

## Initial Roadmap

### R0. Retained Corpus Inventory

Goal: inventory existing eval suites, materialized corpora, retained reports,
gate outputs, and coverage gaps.

Why first: prevents duplicate corpus work and gives the next child a concrete
target.

### R1. Coverage Gap Prioritization

Goal: choose the highest-value corpus expansion target from the inventory.

Why second: broad coverage is more valuable than more same-page-specific tuning.

### R2. New Retained Slice Materialization

Goal: add or refresh one retained corpus slice with bounded fixture metadata and
repeatable local commands.

Why third: future gates need more real-world shape before new behavior changes.

### R3. Post-Default-On Monitoring Batch

Goal: produce a repeatable batch summary comparing same-page default-on metrics
across all retained slices.

Why fourth: the project needs a single command/report that tells whether the
default-on baseline is still healthy.

## Not In Scope

- Agentic behavior changes.
- Source-specific ranking boosts.
- Live provider dependence in default tests.
- Committing fetched third-party content or generated `.tmp` reports.
