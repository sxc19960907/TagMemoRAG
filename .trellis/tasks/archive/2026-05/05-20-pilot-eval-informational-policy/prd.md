# Pilot eval informational policy

## Goal

Let the production pilot eval diagnosis distinguish blocking fixture-review risk from explicitly accepted informational/stress-test suites, so pilot reports are actionable instead of warning on known production-embedder limitations.

## Confirmed Facts

- `scripts/run_eval_ci.py` already supports `--informational-suites` as a comma-separated list whose failures are printed but do not gate CI.
- `tagmemorag pilot run` can include an `eval_reauthoring_diagnosis` stage when both hashing and production baselines are supplied.
- The current pilot stage status is `warning` whenever any diagnosed suite has `severity > 0`.
- Existing docs identify `cross_kb_negatives.jsonl`, `fault_codes.jsonl`, `model_numbers.jsonl`, and `tag_cooccurrence.jsonl` as known stress-test suites for the production embedder, not fixture bugs.

## Requirements

- Add an informational-suite policy to the shared eval reauthoring diagnosis without hiding the original status, severity, metrics, deltas, recommendations, or reasons.
- Expose the policy through `scripts/diagnose_eval_reauthoring.py` and `tagmemorag pilot run` using a comma-separated `--informational-suites` option consistent with `scripts/run_eval_ci.py`.
- Pilot stage status must be based on blocking, non-informational severities:
  - `passed` when all non-ok diagnoses are informational.
  - `warning` when at least one non-informational suite has severity above zero.
  - `failed` remains reserved for invalid/missing diagnosis inputs.
- JSON and Markdown outputs must make informational suites visible to reviewers.
- Preserve backward compatibility for existing callers that do not pass informational suites.
- Keep pilot reports sanitized; do not include raw eval queries, snippets, vectors, source-file lists, API keys, or provider payloads.

## Acceptance Criteria

- [ ] `diagnose_reauthoring(..., informational_suites=...)` marks matching suites as informational while preserving original classification fields.
- [ ] Diagnosis summaries include both all-suite highest severity and blocking-only highest severity.
- [ ] `scripts/diagnose_eval_reauthoring.py --informational-suites a.jsonl,b.jsonl` emits the informational markers in JSON/Markdown.
- [ ] `tagmemorag pilot run --hashing-baseline ... --production-baseline ... --informational-suites ...` passes the policy into the diagnosis stage.
- [ ] Pilot status uses blocking-only severity for diagnosis warnings.
- [ ] Unit tests cover shared diagnosis, script CLI, pilot service, and `tagmemorag` CLI wiring.
- [ ] Docs show how to run pilot with informational stress-test suites.

## Out of Scope

- Changing baseline metrics or eval fixtures.
- Changing `scripts/run_eval_ci.py` semantics.
- Adding a persistent policy file; this task is CLI/report policy only.

## Notes

- Known stress-test list from current docs: `cross_kb_negatives.jsonl`, `fault_codes.jsonl`, `model_numbers.jsonl`, `tag_cooccurrence.jsonl`.
