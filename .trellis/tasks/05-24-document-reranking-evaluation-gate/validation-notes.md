# Validation Notes

## Commands

```text
rg -n "reranking evaluation gate|reranking_eval_gate|ranking pressure" \
  README.md docs/eval-baseline-workflow.md
```

Observed:

- README contains the reranking evaluation gate example.
- `docs/eval-baseline-workflow.md` contains the workflow section and exit-code
  semantics.

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --format markdown
```

Observed:

- status: `passed`
- eight checks rendered in Markdown.

## Scope Check

This task changed docs and Trellis task artifacts only. Runtime behavior and
test code were not modified.
