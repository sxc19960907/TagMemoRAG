# Candidate-aware reranking gate batch

## Goal

Make the repeatable reranking gate batch accept explicit candidate ranking-pressure reports from eval outputs so same-page ordering validation does not rely on manual command stitching.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
# Candidate-Aware Reranking Gate Batch

## Problem

The stability program now has a validated default-off same-page ordering flag,
but the final validation still required a manual two-step sequence:

1. run `tagmemorag eval run` with the candidate config
2. run `diag_general_web_ranking_pressure.py` to produce the candidate pressure
   report, then pass that report into `reranking_gate_batch.py`

That manual seam is easy to forget or vary across future candidate tasks. The
batch gate should accept a candidate eval report directly and derive the bounded
ranking-pressure artifact itself.

## Goals

- Add a candidate-eval-report input to the reranking gate batch.
- Generate a bounded candidate ranking-pressure report inside the batch output
  directory when the candidate eval report is provided.
- Reuse one implementation for the ranking-pressure diagnostic so script and
  batch behavior cannot drift.
- Preserve current CLI behavior for callers that already pass
  `--candidate-ranking-pressure`.
- Keep reports privacy-bounded: no raw query text, raw snippets, `actual_top_k`,
  vectors, provider responses, or secrets in committed/batch summary reports.

## Non-Goals

- Do not turn `search.same_page_ordering_enabled` on by default.
- Do not run retrieval/eval automatically inside the batch command.
- Do not change release-readiness thresholds.
- Do not commit generated `.tmp/` reports.

## Acceptance Criteria

- `scripts/reranking_gate_batch.py` supports a candidate eval report argument
  and writes a derived candidate ranking-pressure JSON report under
  `--output-dir`.
- If both a candidate pressure report and candidate eval report are supplied,
  the explicit pressure report remains authoritative.
- Existing batch behavior, summary schema, and exit codes remain compatible.
- Focused unit tests cover derived candidate pressure, explicit pressure
  precedence, CLI wiring, and privacy omissions.
- Focused tests pass, and a local batch run using the latest same-page enabled
  eval report passes if the `.tmp` artifact is present.
