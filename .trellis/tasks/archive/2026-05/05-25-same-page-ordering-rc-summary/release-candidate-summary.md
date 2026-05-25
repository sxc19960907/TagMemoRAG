# Same-Page Ordering Release Candidate Summary

## Status

- Candidate: `search.same_page_ordering_enabled=true`
- Runtime default: `false`
- Minimum group size: `search.same_page_ordering_min_group_size=2`
- Recommendation: ready for a default-on decision review, not yet default-on.
- Rollback: set `search.same_page_ordering_enabled=false` or remove the
  override from YAML/env config.

## Validation Matrix

| Slice | Mode | Cases | Hit@k | Recall@k | MRR | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| general-web | retained baseline | 7 | 1.000000 | 0.971429 | 0.773810 | passed |
| general-web | same-page enabled | 7 | 1.000000 | 0.971429 | 1.000000 | passed |
| mixed-domain | same-page enabled | 4 | 1.000000 | 1.000000 | 1.000000 | passed |
| multiformat | retained baseline | 3 | 1.000000 | 1.000000 | 0.777778 | passed |
| multiformat | same-page enabled | 3 | 1.000000 | 1.000000 | 0.777778 | passed |
| realmanuals | retained baseline | 10 | 1.000000 | 0.966667 | 0.775000 | passed |
| realmanuals | same-page enabled | 10 | 1.000000 | 0.966667 | 0.825000 | passed |

## Gate Results

- Reranking gate batch: `passed`
- Release readiness: `passed`
- Reranking gate: `passed`
- Failed checks: `[]`
- Candidate general-web ranking pressure:
  - ranking pressure count: `0`
  - highest pressure rank count: `0`

## Safety Notes

- The candidate originally over-reordered some multiformat and realmanuals
  rank-1 cases during Child 9 validation.
- The runtime helper now preserves rank 1 when:
  - rank 1 has an original score lead of at least `0.15`
  - an equivalent-score peer is not more useful than rank 1
  - rank 1 usefulness is already sufficient
- These guards are runtime-visible and do not depend on eval labels.
- The feature remains default-off, so baseline release behavior is unchanged
  unless an operator explicitly enables the setting.

## Artifact References

Generated reports are retained under `.tmp/eval/` and are not committed.
Relevant retained paths:

- `.tmp/eval/same-page-enabled-general-web-cross-guard.json`
- `.tmp/eval/same-page-enabled-mixed-domain.json`
- `.tmp/eval/same-page-enabled-multiformat-cross-guard.json`
- `.tmp/eval/same-page-enabled-realmanuals-cross-guard.json`
- `.tmp/eval/program-same-page-cross-domain-guard-gate/batch-summary.json`
- `.tmp/eval/program-same-page-cross-domain-guard-gate/reranking-gate.json`
- `.tmp/eval/program-same-page-cross-domain-guard-gate/candidate-ranking-pressure.json`

## Decision

Classify this release candidate as `ship-for-review`: the implementation and
guard evidence are stable enough for a default-on decision review, but the
default should stay off until that review explicitly approves the rollout.
