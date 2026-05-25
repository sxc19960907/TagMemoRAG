# Find Real Benchmark Retrieval Gaps

## Goal

Use the corrected real-document benchmarks to identify the next genuine RAG weakness before making more optimization changes.

## Requirements

- Run the real public-web, multi-format, mixed-domain, and real-manual diagnostics that are available locally.
- Inspect per-case metrics and top-k evidence for weak cases.
- Decide whether the next step should be a targeted algorithm/parser/answer fix or a broader benchmark expansion.
- Do not tune against synthetic data or malformed expectations.

## Acceptance Criteria

- [x] A retained diagnostic summary identifies the weakest real benchmark cases and likely cause.
- [x] If a clear bug or narrow improvement exists, implement and verify it.
- [x] If no narrow fix is justified, document the baseline and recommended next task.

## Out of Scope

- Do not add new web sources in this task.
- Do not enable WAVE or experimental rerankers without evidence.
