# Pilot eval accepted suite policy

## Goal

Let pilot eval diagnosis distinguish suites that still need review from suites whose production-embedder divergence has already been reviewed and accepted, so pilot reports can pass when only accepted differences remain.

## Confirmed Facts

- `eval_reauthoring_diagnosis` already supports `informational_suites`, which keeps stress-test suites visible but non-blocking.
- After applying the stress-test informational list, current committed baselines still produce blocking warnings for `mixed_language.jsonl`, `product_manuals.jsonl`, `coffee.jsonl`, and `tag_rerank_edge.jsonl`.
- Phase B review history says `product_manuals`, `mixed_language`, and `tag_rerank_edge` are already good enough and should not trigger fixture rewrites.
- `coffee.jsonl` was relabeled in Phase A but current aggregate production metrics are still lower than hashing; it should remain visible unless the operator explicitly accepts it.

## Requirements

- Add an accepted-suite policy to shared eval reauthoring diagnosis without changing original status, severity, metrics, deltas, recommendations, or reasons.
- Expose the policy through `scripts/diagnose_eval_reauthoring.py` and `tagmemorag pilot run` with a comma-separated `--accepted-suites` option.
- Accepted suites must be visible in JSON/Markdown/stage detail.
- Pilot diagnosis blocking severity must exclude both informational and accepted suites.
- Backward compatibility: existing calls with no accepted suites behave exactly as they do today.
- Keep accepted suites distinct from informational suites:
  - informational = known stress/monitor suite whose failure is non-gating.
  - accepted = reviewed production-embedder divergence or known lower-than-hashing metric that does not need further action for this pilot.

## Acceptance Criteria

- [ ] `diagnose_reauthoring(..., accepted_suites=...)` marks matching suites as accepted while preserving original classification fields.
- [ ] Diagnosis summaries include `accepted_count`, `accepted_suites`, and blocking-only counts that exclude accepted suites.
- [ ] The standalone diagnosis CLI supports `--accepted-suites`.
- [ ] `tagmemorag pilot run` supports `--accepted-suites` and passes it into the diagnosis stage.
- [ ] A pilot run with stress-test suites informational and reviewed strict suites accepted can pass when no other stage fails.
- [ ] Unit tests cover shared diagnosis, script CLI, pilot service, and `tagmemorag` CLI wiring.
- [ ] Docs explain the recommended accepted suite list for the current Phase B decision.

## Out of Scope

- Rewriting eval fixture JSONL files.
- Changing baseline metrics.
- Persisting accepted-suite policy in config files.
- Treating accepted suites as `ok`; original diagnosis must remain visible.
