# Validation Notes

## Commands

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --format markdown \
  --output .tmp/eval/github-ranking-pressure-root-cause.md
```

Observed:

- Items: `2`
- `github-hello-world-repository`: first match rank `6`, recall `1.0`,
  MRR `0.166667`, pressure ranks `5`.
- `github-hello-world-pull-request`: first match rank `4`, recall `1.0`,
  MRR `0.25`, pressure ranks `3`.

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
  --output .tmp/eval/github-ranking-pressure-general-web.json
```

Observed:

- `cases=7`
- `hit@k=1.0`
- `recall_at_k=0.971429`
- `mrr=0.773810`
- `passed=true`

## Decision Check

No runtime code was changed. The diagnosis remains compatible with the current
release-readiness posture: passed baseline, with GitHub ranking pressure kept as
non-blocking visibility for a future broader reranking batch.

## Privacy

Generated `.tmp` reports were not staged. The committed task notes contain only
bounded aggregate metrics and case identifiers from checked-in fixtures.
