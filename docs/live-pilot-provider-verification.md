# Live Pilot Provider Verification Evidence

Date: 2026-05-21

## Scope

This verification ran the unified production-provider pilot path with local Qdrant/MinIO, SiliconFlow embedding/reranker, and DeepSeek answer provider.

Runtime reports are retained locally under `.tmp/production-provider-verification/live-pilot/` and are intentionally not committed.

## Commands

Primary check-only gate:

```bash
uv run python -m tagmemorag production-provider verify \
  --level pilot \
  --config examples/config/production-provider-verification.yaml \
  --check-only
```

Full live pilot gate, reusing already-running local provider services:

```bash
uv run python -m tagmemorag production-provider verify \
  --level pilot \
  --config examples/config/production-provider-verification.yaml \
  --skip-docker \
  --pilot-suite tests/fixtures/eval/coffee.jsonl \
  --pilot-docs tests/fixtures \
  --pilot-hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --pilot-production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --pilot-informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl \
  --pilot-accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl
```

## Result

Top-level verify status: `failed`

The smoke portion passed, but the retained pilot gate failed. This is a valid blocking result for opening pilot traffic; thresholds were not changed during this verification.

Top-level checks:

| Check | Status |
| --- | --- |
| `required_env` | `passed` |
| `docker_providers` | `skipped` |
| `s3_bucket` | `passed` |
| `production_provider_smoke` | `passed` |
| `production_pilot` | `failed` |

## Provider Smoke Evidence

Nested smoke status: `passed`

| Stage | Status |
| --- | --- |
| `config_validate` | `passed` |
| `provider_probe` | `passed` |
| `qdrant_reset` | `passed` |
| `manual_import` | `passed` |
| `blob_verify` | `passed` |
| `manual_library_rebuild` | `passed` |
| `qdrant_inspect` | `passed` |
| `reranker_evidence` | `passed` |
| `answer_smoke` | `passed` |

Key smoke metrics:

- Provider probes: `{'passed': 5}`
- Imported manuals: `1`
- Embedded chunks: `185`
- Qdrant point count: `185`
- Missing vectors: `0`
- Answer kind: `answer`
- Answer citations: `3`
- Retrieve citations: `20`

## Pilot Evidence

Pilot status: `failed`

| Stage | Status |
| --- | --- |
| `config_validate` | `passed` |
| `provider_probe` | `passed` |
| `readiness_smoke` | `passed` |
| `eval` | `failed` |
| `eval_reauthoring_diagnosis` | `warning` |

Eval gate:

- Suite: `coffee.jsonl`
- Cases: `7`
- Top K: `5`
- Precision@K: `0.314286`
- Recall@K: `0.738095`
- MRR: `1.000000`
- Hit@K: `1.000000`
- Required recall@K: `0.750000`
- Failed cases: `__suite__`
- Error: `EvalThreshold: suite recall_at_k 0.738095 < 0.750000`

Diagnosis stage:

- Status: `warning`
- Suite count: `8`
- Highest blocking severity: `1`
- Blocking status counts: `{'monitor': 1}`
- Overall status counts: `{'investigate': 2, 'monitor': 2, 'reauthor': 4}`

## Operational Notes

- The first full run without `--skip-docker` attempted to create new Compose containers while older local Qdrant/MinIO containers were already bound to ports 6333 and 9000. The check-only gate showed Docker startup can pass once the environment is clean, and the final verification intentionally used `--skip-docker` to reuse the already-running services.
- One embedding readiness probe failed transiently during the first full run. A direct embedding probe rerun passed, and the subsequent smoke provider probe passed all five providers.
- DeepSeek was not the blocker in this run. The answer smoke returned an answer with validated citations.

## Decision

Do not mark the live provider pilot gate as passed yet. The next corrective task should inspect or reauthor the SiliconFlow `coffee.jsonl` eval expectations, or choose a pilot owner-approved suite/threshold policy. Until that decision is made, this result remains a failed pilot gate with a passing live smoke path.
