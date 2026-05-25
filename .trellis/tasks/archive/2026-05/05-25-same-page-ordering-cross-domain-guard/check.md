# Check Notes

## Validation

- Focused adjacent tests:
  `.venv/bin/pytest tests/unit/test_eval_runner.py tests/unit/test_retrieval.py tests/unit/test_config_env.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
  - Result: `99 passed`

- Enabled general-web eval:
  - cases: `7`
  - hit@k: `1.000000`
  - recall@k: `0.971429`
  - MRR: `1.000000`

- Enabled mixed-domain eval from retained Child 7 run:
  - cases: `4`
  - hit@k: `1.000000`
  - recall@k: `1.000000`
  - MRR: `1.000000`

- Enabled multiformat eval:
  - docs: `.tmp/multiformat-real-knowledge/multiformat_real`
  - cases: `3`
  - hit@k: `1.000000`
  - recall@k: `1.000000`
  - MRR: `0.777778`
  - baseline MRR: `0.777778`

- Enabled realmanuals eval:
  - docs: `.tmp/product-manuals-pdf-only`
  - cases: `10`
  - hit@k: `1.000000`
  - recall@k: `0.966667`
  - MRR: `0.825000`
  - baseline MRR: `0.775000`
  - Note: PDF parser emitted existing `Rotated text discovered` warnings.

- Reranking gate batch with derived candidate pressure:
  - status: `passed`
  - release readiness: `passed`
  - reranking gate: `passed`
  - failed checks: `[]`

## Discovery

The first multiformat run exposed a regression: MRR dropped to `0.500000`
because the same-page ordering heuristic overrode strong original ranking in
MDN/IRS-style same-page groups. A later realmanuals run exposed a similar
rank-1 table-heading regression in an oven manual. The fix added conservative
runtime-visible guards:

- preserve rank 1 when its original score lead is at least `0.15`
- preserve rank 1 when an equivalent-score peer is not more useful

These guards preserved the general-web GitHub improvement while restoring
cross-domain stability.

## Privacy

Generated full eval reports remain under `.tmp` and were not committed. The
committed notes include only summary metrics and paths. Bounded gate/pressure
artifacts were scanned for forbidden markers:

- `actual_top_k`
- `raw snippet`
- `provider_response`
- `embedding`
- `vector`
- `Authorization`
- `api_key`

No matches were found in the bounded artifacts.
