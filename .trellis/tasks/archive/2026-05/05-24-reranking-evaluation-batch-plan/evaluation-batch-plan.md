# Reranking Evaluation Batch Plan

## Purpose

This plan defines the validation contract for any future general-purpose
reranking or evidence-usefulness change.

The immediate GitHub Hello World pressure cases are real, but they are too thin
to tune against directly. A future runtime ranking change must improve or at
least explain those cases while preserving the full release-readiness baseline.

## Candidate Scope

Acceptable candidates:

- A deterministic evidence-usefulness scorer that can be evaluated offline.
- A first-class reranker integration or reranker configuration change.
- A context-selection scoring adjustment, if the change only affects context
  packing and not retrieval ordering.

Out of scope for this evaluation batch:

- GitHub-specific source boosts.
- Broad lexical boosts justified only by the two GitHub cases.
- Changes that require live network access in default tests.
- Changes that make Qdrant or any external provider authoritative for final
  ranking without a separate PRD.

## Required Baseline Commands

Run the current release slices before and after any candidate change.

```text
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8 \
  --min-recall-at-k 0.0 \
  --min-mrr 0.0 \
  --min-hit-at-k 0.0 \
  --output .tmp/eval/rerank-batch-general-web.json
```

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/rerank-batch-general-web.json \
  --output .tmp/eval/rerank-batch-ranking-pressure.json
```

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_retrieval=.tmp/eval/rerank-batch-general-web.json \
  --report general_web_ranking_pressure=.tmp/eval/rerank-batch-ranking-pressure.json \
  --output .tmp/eval/rerank-batch-release-readiness.json
```

The future implementation task should add or reuse the equivalent commands for
the retained mixed-domain, multi-format, real-manual, context-quality, and
answer-quality reports used by `scripts/release_readiness.py`.

## Ship Gate

A future runtime ranking change may ship only if all are true:

- Release readiness remains `passed`.
- General-web `hit@k` remains `1.0`.
- General-web `recall_at_k` does not decrease from `0.971429`.
- General-web `MRR` does not decrease from `0.773810`.
- Mixed-domain, multi-format, and real-manual retrieval stages remain at least
  their current release-readiness statuses.
- Context-quality normal and tight-budget stages remain at least their current
  release-readiness statuses.
- Answer-quality diagnostics remain green.
- Ranking-pressure count does not increase above `2`.
- Highest pressure rank count does not increase above `5`.
- Any improvement to the GitHub cases is documented as a byproduct of a generic
  signal, not a source-specific special case.

## GitHub Pressure Measurement

Track these case-level values from the ranking-pressure diagnostic:

- `github-hello-world-repository`
  - baseline first matched rank: `6`
  - baseline pressure ranks: `5`
  - baseline MRR: `0.166667`
- `github-hello-world-pull-request`
  - baseline first matched rank: `4`
  - baseline pressure ranks: `3`
  - baseline MRR: `0.25`

Improvement is useful but not required for release. Regression is a warning:
first matched rank should not move later for either case unless the fixture
expectation is explicitly refined in a separate task.

## Privacy And Artifact Rules

Do not commit generated `.tmp` reports. Committed summaries may include bounded
metrics, case ids from checked-in fixtures, stage names, counts, and boolean
status values.

Do not commit or emit by default:

- raw query text,
- raw snippets or full result text,
- `actual_top_k` / full candidate lists,
- vectors or embeddings,
- provider response bodies,
- API keys or secrets,
- high-cardinality absolute paths.

## Recommended Next Implementation Task

Implement a reusable candidate evaluation runner only after this plan is
accepted. The runner should compare baseline and candidate reports, produce a
bounded JSON/Markdown delta, and fail if the ship gate is violated.
