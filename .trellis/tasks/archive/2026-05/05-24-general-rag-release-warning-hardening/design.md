# Design

## Scope

This task is a bounded general-purpose RAG hardening batch for the existing
classic retrieval and answer stack. It follows the release-readiness warning
list from the archived long-horizon quality program.

## Boundaries

- Classic `/retrieve` and `/answer` behavior remains the implementation target.
- Agentic mode stays default-off and untouched.
- WAVE/geodesic remains experimental/default-off and is not promoted.
- External rerankers remain outside the critical path.
- Runtime-fetched third-party content stays under `.tmp/` and out of git.

## Work Streams

1. Warning diagnostics
   - Inspect retained reports for `general_web_retrieval` and
     `multiformat_context_tight`.
   - Write a short task-local diagnostic note that names the weak cases,
     observed ranks, context selection behavior, and rejected tuning risks.

2. Ranking hardening
   - Prefer local deterministic evidence usefulness changes that are bounded to
     public-web body evidence.
   - Avoid broad additive priors that override the core vector/graph/lexical
     score; prior work showed this can regress recall.
   - Keep identity metadata useful for narrowing but separate from ordinary
     topic evidence.

3. Tight-context hardening
   - Prefer context-level compression or same-source evidence packing when it
     can preserve evidence lineage and citation ids.
   - Do not reshape parser chunks globally unless diagnostics prove a localized
     context/evidence strategy cannot solve the warning safely.

4. Release gate
   - Regenerate retained reports.
   - Run release readiness against the latest report paths.
   - Keep warning status honest if a warning cannot be safely reduced in this
     batch.

## Compatibility

API response schemas should remain unchanged. If context packing changes, it
may reorder or merge `context_pack.items`, but must preserve existing evidence,
citations, `evidence_refs`, `citation_ids`, and compatibility fields.

Ranking changes must remain deterministic over loaded graph nodes and vectors.
Diagnostics and reports must not emit raw secrets, vectors, provider bodies, or
unbounded document text.

## Rollback

Each kept code change should be small enough to revert independently. If a
tuning attempt improves one warning but regresses another passed slice, reject
it and document the result rather than carrying the regression.
