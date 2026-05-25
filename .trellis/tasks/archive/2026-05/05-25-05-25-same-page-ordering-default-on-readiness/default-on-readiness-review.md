# Same-Page Ordering Default-On Readiness Review

## Decision

Decision: `propose-default-on`

The same-page ordering flag is ready for a default-on rollout proposal, but
this task does not change the runtime default. The current default remains:

- `search.same_page_ordering_enabled=false`
- `search.same_page_ordering_min_group_size=2`

The proposed rollout should be a separate implementation task that flips the
default only after re-running the focused tests and candidate-aware gate batch.

## Evidence Summary

| Evidence | Result | Readiness Impact |
| --- | --- | --- |
| Runtime default-off wiring | Passed | Existing deployments keep baseline behavior. |
| General-web enabled eval | MRR `0.773810` -> `1.000000` | Removes retained same-page ranking pressure. |
| Mixed-domain enabled guard | MRR `1.000000` | No observed regression in retained mixed-domain slice. |
| Multiformat enabled guard | MRR `0.777778` -> `0.777778` | Matches retained baseline after safety refinement. |
| Realmanuals enabled guard | MRR `0.775000` -> `0.825000` | Improves retained manual slice without recall loss. |
| Candidate ranking pressure | Count `0`, highest pressure rank count `0` | Candidate resolves retained general-web pressure. |
| Reranking gate batch | `passed` | Candidate satisfies the batch release gate. |
| Release readiness | `passed` | No release-readiness degradation recorded. |
| Reranking gate | `passed`, failed checks `[]` | No gate-level blocking regressions recorded. |

## Safety Review

The candidate originally over-reordered some rank-1 cases in multiformat and
realmanuals retained slices. Child 9 converted that discovery into runtime
guards instead of label-only eval exceptions:

- preserve rank 1 when it has an original score lead of at least `0.15`
- preserve rank 1 when an equivalent-score peer is not more useful
- preserve rank 1 when usefulness is already sufficient

These guards are important enough that a default-on implementation task should
keep dedicated tests for them. The default-on change should be treated as a
configuration default change, not as permission to broaden the heuristic.

## Residual Risks

- Retained validation slices are small, especially mixed-domain and
  multiformat.
- The candidate targets same-page/same-header pressure and should not be
  generalized to unrelated cross-source ranking behavior.
- Operators may have existing eval expectations based on strict original-score
  ordering within same-page result groups.

## Rollout Requirements

Before flipping the default, run a separate default-on task that:

- changes only the default value for `search.same_page_ordering_enabled`
- keeps `search.same_page_ordering_min_group_size=2`
- reruns focused retrieval, eval-runner, reranking gate batch, and release
  readiness checks
- records a bounded before/after evidence summary
- preserves an explicit rollback path

## Rollback

Rollback is configuration-only if the default-on task ships:

- set `search.same_page_ordering_enabled=false` in YAML or environment config
- or revert the default value change while keeping the guarded implementation
  and tests

## Next Step

Open a dedicated default-on implementation child task if the project owner
accepts this proposal. If not, keep the feature opt-in and continue collecting
larger retained-corpus evidence before revisiting the default.
