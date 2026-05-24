# Validation Notes

## Change

Updated only `tests/fixtures/eval/general_web.jsonl`.

The MDN `mdn-http-cache-no-cache-private` case now recognizes additional
independently useful evidence chunks that already appear in top-k:

- private cache is tied to a specific client and can store a personalized
  response
- personalized content should be stored only in the private cache with a
  `private` directive
- combined `no-cache, private` guidance that prevents sharing personalized
  content with other users

GitHub expected evidence was intentionally unchanged. Those cases remain
ranking pressure for a later retrieval-quality task.

## Results

Fixture load:

- `7` cases loaded
- MDN case has `5` relevant entries and `top_k_override=8`

Unit validation:

- `.venv/bin/pytest tests/unit/test_run_eval_ci.py -q`
  - `1 passed`

General-web retrieval:

```text
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8 \
  --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 \
  --output .tmp/eval/general-web-after-evidence-refinement.json
```

Result:

- `cases=7`
- `hit@k=1.000000`
- `recall@k=0.971429`
- `MRR=0.773810`

This improves over the previous release-readiness general-web retrieval
baseline:

- previous `recall@k=0.928571`
- previous `MRR=0.651361`

Release readiness after refreshing the default general-web retrieval report:

- `.tmp/eval/release-readiness-after-evidence-refinement.json`
- status: `passed`

## Rationale

This is an eval-label correction, not a ranking workaround. The newly counted
MDN chunks directly answer the query and were already ranked in top-k by the
existing retrieval system. Runtime retrieval behavior is unchanged.
