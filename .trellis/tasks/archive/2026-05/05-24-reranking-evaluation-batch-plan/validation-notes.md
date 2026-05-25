# Validation Notes

## Commands

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/reranking-plan-release-readiness.json
```

Observed:

- status: `passed`
- `general_web_retrieval.ranking_pressure_count=2`
- `general_web_retrieval.highest_pressure_rank_count=5`
- `general_web_retrieval.hit_at_k=1.0`
- `general_web_retrieval.recall_at_k=0.971429`
- `general_web_retrieval.mrr=0.773810`

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --output .tmp/eval/reranking-plan-ranking-pressure.json
```

Observed:

- `ranking_pressure_count=2`
- `highest_pressure_rank_count=5`
- `github-hello-world-repository`: first matched rank `6`, pressure ranks `5`,
  MRR `0.166667`.
- `github-hello-world-pull-request`: first matched rank `4`, pressure ranks `3`,
  MRR `0.25`.

## Decision Check

This task changed only Trellis planning artifacts. Runtime retrieval behavior,
fixtures, tests, release-readiness gates, and generated `.tmp` reports were not
committed.

## Privacy

Committed notes contain only bounded metrics and checked-in fixture case ids.
Raw queries, snippets, full candidate lists, vectors, secrets, and generated
`.tmp` reports remain uncommitted.
