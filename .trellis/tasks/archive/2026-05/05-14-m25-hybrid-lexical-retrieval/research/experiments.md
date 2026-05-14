# M25 Hybrid Lexical Retrieval Experiments

Date: 2026-05-14

All runs used the deterministic hashing embedder so results are offline and reproducible:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64
```

## Baseline: product manuals exact local before lexical

- Change: Added lexical-sensitive product-manual fixture cases, then ran current vector/WAVE behavior before production lexical changes.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m25-product-baseline \
  --output .tmp/eval/m25-reports/product-baseline.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate: `precision_at_k=0.142857`, `recall_at_k=0.785714`, `mrr=0.785714`, `hit_at_k=0.785714`.
- Failing cases: `washer-pump-short-zh`, `washer-child-lock-short-zh`, `ac-f07-short-code`.
- Decision: Baseline exposed enough exact-term weakness to justify bounded production lexical retrieval.

## Post-change: product manuals with hybrid lexical

- Change: Enabled bounded local lexical scan, lexical source seeding, lexical score hints, ANN candidate union, cache suffix, safe debug metadata, and eval config snapshot fields.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m25-product-post \
  --output .tmp/eval/m25-reports/product-post.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate: `precision_at_k=0.214286`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`.
- Result: The three short exact-term misses recovered without aggregate product regression.

## Regression check: coffee smoke suite

- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m25-coffee-post \
  --output .tmp/eval/m25-reports/coffee-post.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate: `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- Result: Matches M23 coffee baseline tracked metrics.
