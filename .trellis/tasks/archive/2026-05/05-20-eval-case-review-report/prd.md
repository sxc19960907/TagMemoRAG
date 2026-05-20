# Eval case review report

## Goal

Turn full eval JSON reports into a bounded case-level review report so production-embedder fixture reauthoring can focus on concrete missing expectations, negative hits, and low-ranking cases without automatically changing fixture ground truth.

## Requirements

- Provide an offline script that reads an existing `tagmemorag eval run --output` JSON report.
- Produce JSON or Markdown output sorted by review priority.
- Highlight cases with eval failures, negative hits, zero hit, low recall, low MRR, or large expected-vs-matched gaps.
- Include enough bounded context for human review: case id, kb, metrics, failures, expected count, matched expected indexes, top result headers/source files, and negative-hit summary.
- Avoid unbounded or sensitive output: no raw query text by default, no full result snippets, no vectors, no full metadata dumps, no API keys.
- Support an opt-in `--include-query` flag for local review when raw queries are acceptable.
- Document how this complements `diagnose_eval_reauthoring.py` and `relabel_eval_fixture.py`.

## Acceptance Criteria

- [ ] The script can summarize a saved eval JSON report without network access.
- [ ] JSON output includes schema version, input report path, summary counts, and per-case review items.
- [ ] Markdown output includes a reviewer-friendly table sorted by severity.
- [ ] Unit tests cover priority classification, query redaction/default safety, Markdown rendering, invalid report handling, and CLI file output.
- [ ] Documentation shows the workflow from aggregate diagnosis to full eval report to case-level review.

## Notes

- This task does not run SiliconFlow and does not edit fixture JSONL.
