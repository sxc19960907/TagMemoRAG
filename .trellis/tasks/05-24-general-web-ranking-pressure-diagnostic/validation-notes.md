# Validation Notes

## Commands

```text
.venv/bin/pytest \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  tests/unit/test_summarize_eval_case_review.py \
  -q
```

Result:

- `13 passed`

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --output .tmp/eval/general-web-ranking-pressure.json
```

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --format markdown \
  --output .tmp/eval/general-web-ranking-pressure.md
```

## Observed Report

The retained general-web report produced:

- `ranking_pressure_count=2`
- `highest_pressure_rank_count=5`
- suite `hit_at_k=1.0`
- suite `recall_at_k=0.971429`
- suite `MRR=0.773810`

Ranking-pressure items:

- `github-hello-world-repository`
  - first matched rank: `6`
  - pressure ranks before first match: `5`
  - recall: `1.0`
  - MRR: `0.166667`
- `github-hello-world-pull-request`
  - first matched rank: `4`
  - pressure ranks before first match: `3`
  - recall: `1.0`
  - MRR: `0.25`

The diagnostic no longer flags the MDN HTTP caching case after the eval-label
refinement. That matches the intended boundary: this report identifies reachable
but under-ranked expected evidence, not top-k misses or fixture-label gaps.

## Privacy Check

Unit tests verify that raw query text and raw result snippets are omitted from
the diagnostic output by default. The generated retained reports live under
`.tmp/eval/` and are not committed.
