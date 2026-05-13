# M23 Retrieval Tuning Experiments

Date: 2026-05-13

All runs used the deterministic hashing embedder to keep the suite offline and reproducible:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing \
TAGMEMORAG__MODEL__NAME=hashing \
TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run ...
```

Reports were written under `.tmp/eval/m23-reports/`. Eval data directories were isolated under `.tmp/eval/m23-*`, so normal `storage.data_dir` was not modified.

## Baseline: coffee exact local

- Hypothesis: Capture current fast smoke-suite behavior before tuning.
- Change: None. Defaults: `top_k=5`, `source_k=3`, `steps=3`, `decay=0.7`, `amplitude_cutoff=0.01`, `aggregate=max`, `metadata_field_boost=0.05`, `tag_boost=0.03`.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-coffee-baseline \
  --output .tmp/eval/m23-reports/coffee-baseline.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate: `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- Decision: Keep as baseline. Coffee smoke eval passed.

## Baseline: product manuals exact local

- Hypothesis: Capture current M20 product-manual suite behavior before tuning.
- Change: None.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-baseline \
  --output .tmp/eval/m23-reports/product-baseline.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate: `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`.
- Decision: Keep as baseline. Product suite was already saturated on the tracked quality metrics, so default changes require especially strong evidence.

## Variant: source_k=4

- Hypothesis: More seed nodes may improve recall on mixed-language/manual-category queries.
- Change: `--source-k 4`.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-source4 \
  --output .tmp/eval/m23-reports/product-source4.json \
  --source-k 4 \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate before: product `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`; coffee `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- Aggregate after: product unchanged; coffee unchanged in `.tmp/eval/m23-reports/coffee-source4.json`.
- Wins: None.
- Regressions: None.
- Decision: Reject as default change. It is safe but has no measured quality gain.

## Variant: steps=2

- Hypothesis: Fewer propagation steps may reduce graph drift while preserving nearby procedural chunks.
- Change: `--steps 2`.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-steps2 \
  --output .tmp/eval/m23-reports/product-steps2.json \
  --steps 2 \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate before: product `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`; coffee `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- Aggregate after: product unchanged; coffee unchanged in `.tmp/eval/m23-reports/coffee-steps2.json`.
- Wins: None.
- Regressions: None.
- Decision: Reject as default change. It is safe on the current suites but not better than `steps=3`.

## Variant: decay=0.55

- Hypothesis: Lower propagation decay may reduce neighbor over-amplification without hurting direct hits.
- Change: `--decay 0.55`.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-decay055 \
  --output .tmp/eval/m23-reports/product-decay055.json \
  --decay 0.55 \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate before: product `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`; coffee `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- Aggregate after: product unchanged; coffee unchanged in `.tmp/eval/m23-reports/coffee-decay055.json`.
- Wins: None.
- Regressions: None.
- Decision: Reject as default change. No measurable gain.

## Variant: aggregate=sum

- Hypothesis: Summing repeated weak paths may improve recall for procedural neighborhoods.
- Change: `--aggregate sum`.
- Command:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-sum \
  --output .tmp/eval/m23-reports/product-sum.json \
  --aggregate sum \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

- Aggregate before: product `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`.
- Aggregate after: product `precision_at_k=0.09375`, `recall_at_k=0.75`, `mrr=0.302083`, `hit_at_k=0.75`.
- Wins: None.
- Regressions: `fridge-temperature-zh` and `ac-mode-zh-en` missed their expected chunk at top-k.
- Decision: Reject. This violates the M23 quality gate and should not become the default.

## Additional Probes

- `source_k=8`, `steps=4`, `decay=0.8`, and combined `metadata_field_boost=0.08` plus `tag_boost=0.05` all preserved product aggregate metrics but did not improve them.
- `steps=1` preserved coffee smoke metrics.
- No recurring category/model/tag mismatch appeared in the accepted product baseline, so metadata-aware unfiltered reranking was not adopted.
- Exact-code product cases (`E21`, `F2`) already passed at top-k in the product baseline, so lexical retrieval is deferred. A future lexical experiment should add harder fault-code cases before changing ranking behavior.

## Final Decision

M23 leaves search defaults unchanged. The suite evidence supports preserving the existing conservative WAVE-RAG settings:

- `source_k=3`
- `steps=3`
- `decay=0.7`
- `amplitude_cutoff=0.01`
- `aggregate=max`
- `metadata_field_boost=0.05`
- `tag_boost=0.03`

The implemented change is tooling: `eval run` now accepts bounded search-parameter overrides and records the effective search settings in `config_snapshot.search`, making future tuning experiments repeatable without editing production config files.
