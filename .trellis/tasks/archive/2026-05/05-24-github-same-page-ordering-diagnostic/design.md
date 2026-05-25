# Design

## Boundary

Add an offline diagnostic that summarizes same-page ordering pressure from an
existing eval JSON report. The diagnostic is a pure report reader and does not
import runtime state, execute retrieval, or alter production scoring.

## Data Flow

1. Load an eval report JSON object from disk.
2. Iterate `cases`, skipping `__suite__`.
3. For each case with `actual_top_k`, compute the first matched rank.
4. Keep only pressure cases where first matched rank is greater than `1`.
5. Convert top-k results to bounded rows:
   - rank
   - score
   - matched flag and matched expected indexes
   - source/header identifiers
   - query coverage
   - usefulness score and cue counts from the existing evidence-usefulness
     diagnostic module
6. Summarize repeated source/header concentration, score gaps, near-ties before
   the first match, and matched/pre-match usefulness differences.

## Reuse

The previous child introduced `tagmemorag.evidence_usefulness_diagnostic`. This
task reuses its bounded usefulness report rather than duplicating cue scoring.
The same-page diagnostic reads that in-memory report contract and adds
rank-local grouping/score-gap summaries.

## Privacy

The module may read raw query/result text from a local eval report to compute
numeric coverage and usefulness, but it must never emit raw query text, result
text, `actual_top_k`, vectors, provider bodies, secrets, or absolute local
paths.

## Compatibility

The schema is versioned as `same_page_ordering_diagnostic.v1`. CLI invalid
input exits with code `2`. JSON and Markdown rendering must remain stable and
bounded.

## Rollback

Rollback is deleting the new module, script, tests, and task artifacts. No
runtime wiring or migrations are involved.
