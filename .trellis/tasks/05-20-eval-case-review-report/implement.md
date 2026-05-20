# Eval case review report implementation plan

## Checklist

- [x] Add `scripts/summarize_eval_case_review.py`.
- [x] Add `tests/unit/test_summarize_eval_case_review.py`.
- [x] Update eval workflow docs and README with aggregate-to-case workflow.
- [x] Generate a small local eval report and summarize it in Markdown.
- [x] Run focused tests and `git diff --check`.
- [ ] Archive task and commit work, archive, and journal.

## Validation Commands

```bash
uv run python -m tagmemorag eval run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --eval-data-dir .tmp/eval-case-review/data \
  --output .tmp/eval-case-review/coffee.json \
  --min-recall-at-k 1.0 \
  --min-mrr 1.0 \
  --min-hit-at-k 1.0

uv run python scripts/summarize_eval_case_review.py \
  --report .tmp/eval-case-review/coffee.json \
  --format markdown

uv run pytest tests/unit/test_summarize_eval_case_review.py tests/unit/test_diagnose_eval_reauthoring.py -q

git diff --check
```

## Rollback Points

- If the review ranking is too opinionated, keep the raw bounded case summary and remove severity labels.
- If report output risks exposing too much content, keep query redacted and reduce top result fields to source/header only.
