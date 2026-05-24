# Evidence usefulness dry run

## Goal

Create an offline, bounded diagnostic that reads an existing eval report and
summarizes whether evidence-like usefulness cues align with matched relevant
results. The diagnostic is observational only: it must not change retrieval
ranking, context packing, eval labels, fixtures, or runtime behavior.

## Requirements

- Read a `tagmemorag eval run --output` JSON report.
- Produce JSON and Markdown summaries with a stable schema version.
- Report only bounded, low-sensitive fields:
  - case id and KB name
  - aggregate eval metrics already present in the report
  - result rank
  - matched boolean and matched expected indexes
  - source file/header identifiers already present in existing diagnostics
  - body word count
  - cue counts
  - numeric query-term coverage
  - numeric usefulness score
- Summarize whether matched evidence tends to score higher than earlier
  unmatched results, especially for currently known ranking-pressure cases.
- Omit raw query text, raw snippets/full result text, vectors/embeddings,
  provider response bodies, `actual_top_k`, full top-result payloads, secrets,
  and high-cardinality absolute paths.
- Keep the diagnostic deterministic and offline. It must not fetch URLs, call
  external providers, rebuild indexes, or invoke live retrieval.
- Preserve existing release readiness and reranking gate behavior.

## Acceptance Criteria

- [ ] A pure Python diagnostic module exists under `src/tagmemorag/`.
- [ ] A thin script entry point exists under `scripts/`.
- [ ] Unit tests cover summary calculations, privacy omissions, Markdown
      rendering, and invalid input handling.
- [ ] Focused tests for the new diagnostic and adjacent gate diagnostics pass.
- [ ] The diagnostic successfully runs against the retained general-web eval
      report when that report is available locally.
- [ ] Parent program log records the dry-run result and the recommended next
      child task.

## Notes

- Parent program: `05-24-general-rag-stability-program`.
- This child intentionally stops before any runtime ranking candidate. A later
  child may use the report to design a candidate, but only behind existing
  gates.
