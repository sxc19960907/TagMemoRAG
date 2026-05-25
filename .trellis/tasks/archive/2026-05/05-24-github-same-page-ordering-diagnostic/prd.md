# GitHub same-page ordering diagnostic

## Goal

Explain why the two GitHub Hello World general-web cases still have low MRR
even though the previous evidence-usefulness dry run shows matched evidence has
stronger usefulness cues than earlier ranks. This child is observational only:
it must diagnose same-page ordering pressure without changing runtime ranking,
fixtures, labels, or context packing.

## Requirements

- Read an existing `tagmemorag eval run --output` JSON report.
- Focus on cases where:
  - the first matched result appears below rank 1; and
  - the top-k window is dominated by one repeated `source_file` or one repeated
    `header`.
- Emit a bounded JSON/Markdown report with per-case ordering diagnostics:
  - case id, KB name, and existing numeric metrics
  - first matched rank and pressure rank count
  - repeated source/header counts
  - retrieval score gap between rank 1 and first matched result
  - score tie/near-tie counts before the first match
  - matched vs pre-match evidence-usefulness score summaries
  - bounded per-rank rows with rank, score, matched flag, source/header
    identifiers, usefulness score, query coverage, and cue counts
- Omit raw query text, raw snippets/full result text, `actual_top_k`, vectors,
  provider bodies, secrets, and high-cardinality absolute paths.
- Keep the diagnostic deterministic, offline, and read-only. It must not fetch
  URLs, run retrieval, rebuild indexes, or call external providers.
- Preserve release-readiness and reranking-gate outcomes.

## Acceptance Criteria

- [ ] A pure diagnostic module exists under `src/tagmemorag/`.
- [ ] A thin CLI script exists under `scripts/`.
- [ ] Unit tests cover same-page detection, score-gap/near-tie summaries,
      privacy omissions, Markdown rendering, and invalid input handling.
- [ ] Focused tests for the new diagnostic and adjacent diagnostics pass.
- [ ] The diagnostic runs against the retained general-web eval report and
      identifies the GitHub Hello World cases as same-page ordering pressure.
- [ ] Parent program log records the result and a safe next recommendation.

## Notes

- Parent program: `05-24-general-rag-stability-program`.
- This task is expected to produce evidence for the next candidate-design
  child. It is not itself a ranking candidate.
