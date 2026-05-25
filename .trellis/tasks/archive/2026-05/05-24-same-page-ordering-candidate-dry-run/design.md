# Design

## Boundary

This task adds an offline candidate simulator. It reads eval output and
produces comparison reports; it does not call retrieval, fetch pages, rebuild
indexes, alter fixtures, or wire a ranking change into production.

## Candidate Shape

For each eval case:

1. Build bounded per-result rows with retrieval score and the usefulness fields
   already produced by `evidence_usefulness_diagnostic`.
2. Detect same-page dominance when the top-k window contains a repeated
   `source_file` or repeated `header`.
3. If same-page dominance exists and the baseline first matched rank is below
   rank 1, sort within the candidate window by:
   - usefulness score descending
   - query-term coverage descending
   - original retrieval score descending
   - original rank ascending
4. Leave rank-1 hits and non-dominated cases in their original order.

The candidate is intentionally simple and local so it can reveal whether a
same-page representative strategy is promising before any runtime design work.
It is pressure-gated to avoid moving already-good rank-1 evidence.

## Metrics

For each case, compute baseline and candidate:

- first matched rank
- MRR
- precision@k
- recall@k
- hit@k
- pressure rank count
- matched rank movement

At suite level, compute averages and counts of improved, unchanged, and
regressed cases. Candidate status is:

- `passed` when there are improvements and no regressions
- `needs_review` when no regression exists but no improvement is observed
- `failed` when any matched case regresses

## Privacy

The module may read raw query and result text from the local report to compute
bounded numeric signals through the existing diagnostic module, but output must
not contain raw queries, snippets, `actual_top_k`, vectors, provider bodies,
secrets, or absolute paths.

## Compatibility

The schema is `same_page_ordering_candidate.v1`. CLI input errors exit `2`.
The module is pure and deterministic.

## Rollback

Rollback is deleting the new module, CLI, tests, and task artifacts. No runtime
state, migrations, or config changes are involved.
