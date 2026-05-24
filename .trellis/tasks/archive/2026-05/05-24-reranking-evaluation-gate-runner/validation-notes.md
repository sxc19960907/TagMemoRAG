# Validation Notes

## Commands

```text
.venv/bin/pytest \
  tests/unit/test_reranking_eval_gate.py \
  tests/unit/test_release_readiness.py \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  -q
```

Result:

- `22 passed`

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/reranking-eval-gate-self-check.json
```

Observed:

- status: `passed`
- check count: `8`
- failed checks: `[]`
- bounded-output check: no `actual_top_k`, `top_results`, raw snippet, or private
  query terms found in the gate report.

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --format markdown
```

Observed:

- Markdown rendered the same 8 passed checks.

```text
.venv/bin/python -m compileall -q \
  src/tagmemorag/reranking_eval_gate.py \
  scripts/reranking_eval_gate.py
```

Result:

- passed

## Privacy

Generated `.tmp` reports were not staged. Committed code and tests keep output
bounded to readiness status, aggregate metrics, pressure counts, and checked-in
fixture case ids.
