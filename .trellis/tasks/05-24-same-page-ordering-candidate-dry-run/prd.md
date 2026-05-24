# Same-page ordering candidate dry run

## Goal

Create an offline candidate dry run for the same-page ordering issue identified
in the general-web GitHub Hello World cases. The dry run should simulate a
bounded reorder within repeated `source_file`/`header` groups and report whether
the candidate improves ranking-pressure metrics without changing runtime
retrieval behavior.

## Requirements

- Read an existing `tagmemorag eval run --output` JSON report.
- Simulate a candidate order only in memory for cases where top-k results are
  dominated by the same `source_file` or the same `header`.
- Use bounded diagnostic signals already available from the existing offline
  diagnostics, including usefulness score, query coverage, retrieval score,
  matched status, and cue counts.
- Emit a JSON/Markdown report with:
  - baseline suite metrics and candidate suite metrics
  - per-case baseline first matched rank and candidate first matched rank
  - per-case baseline MRR and candidate MRR
  - rank movement for matched evidence
  - count of improved, unchanged, and regressed cases
  - ranking-pressure count before and after
  - a candidate status of `passed`, `needs_review`, or `failed`
- Preserve privacy constraints: no raw query text, raw snippets/full result
  text, `actual_top_k`, vectors/embeddings, provider bodies, secrets, or
  high-cardinality absolute paths in output.
- Do not change runtime ranking, retrieval, context packing, eval fixtures, or
  release readiness gates.
- The report must be suitable as input evidence for a later design decision,
  not as an automatic runtime rollout approval.

## Acceptance Criteria

- [ ] A pure dry-run module exists under `src/tagmemorag/`.
- [ ] A thin CLI script exists under `scripts/`.
- [ ] Unit tests cover improvement, no-op, regression detection, privacy
      omissions, Markdown rendering, and invalid input handling.
- [ ] Focused adjacent tests pass.
- [ ] The retained general-web report dry run shows whether the same-page
      candidate improves the GitHub low-MRR cases.
- [ ] Parent program log records the result and the next recommended child.

## Notes

- Parent program: `05-24-general-rag-stability-program`.
- Runtime ranking remains unchanged in this child.
