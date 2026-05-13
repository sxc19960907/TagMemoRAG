# implement.md - M23 Retrieval Tuning Experiments

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review M19/M20/M22 artifacts and current search/eval code.
- [x] Run exact-local baseline evals for coffee and product-manual suites.
- [x] Save compact baseline findings to `research/experiments.md`.
- [x] Evaluate at least three bounded search-parameter variants.
- [x] Record each variant with hypothesis, command, metrics, wins, regressions, and decision.
- [x] Decide whether any default search config should change.
- [x] If defaults change, update `src/tagmemorag/config.py`, `config.yaml`, README examples, and env/config tests if needed. No default changed; `config.yaml` was synchronized with existing default fields.
- [x] If ranking behavior changes, keep it local, deterministic, safe, and covered by focused tests. No ranking behavior changed.
- [x] Verify API/CLI request-level search parameter overrides still work.
- [x] Verify eval reports remain backward compatible and low-sensitivity.
- [x] Update README or adjacent docs with final tuning guidance and reproduction commands.
- [ ] Curate `implement.jsonl` and `check.jsonl` with relevant spec/research docs before implementation if using sub-agents.

## Suggested Experiment Order

1. Baseline exact-local:
   - coffee suite
   - product-manual suite
2. One-axis parameter sweeps:
   - `source_k`
   - `steps`
   - `decay`
   - `aggregate`
3. Filter/metadata boost checks:
   - `metadata_field_boost`
   - `tag_boost`
4. Combined variant only if individual results point in the same direction.
5. Optional metadata-aware or lexical experiment only if baseline failures justify it.

## Validation

Baseline commands:

```bash
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-coffee-baseline

uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-baseline
```

Focused tests after any code changes:

```bash
uv run pytest tests/unit/test_graph_wave.py tests/unit/test_eval_runner.py tests/unit/test_cli.py tests/unit/test_api.py -q
uv run pytest tests/e2e/test_eval_cli.py -q
```

Qdrant/ANN regression checks when touching ANN or candidate behavior:

```bash
uv run pytest tests/unit/test_manual_library.py tests/unit/test_storage_state.py tests/unit/test_api.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm every adopted change has eval evidence.
- Confirm aggregate product-manual metrics do not regress versus baseline.
- Confirm per-case regressions are documented and acceptable.
- Confirm final ranking remains local WAVE-RAG.
- Confirm no new live Qdrant/network requirement enters default tests.
- Confirm no raw vectors, secrets, private document text, full candidate id lists, or high-cardinality paths are added to reports/logs/metrics.
- Confirm docs and config examples match actual defaults.

## Rollback Points

- If parameter sweeps are inconclusive, leave defaults unchanged and finish with experiment documentation.
- If a ranking helper creates broad regressions, remove it and keep the evidence as a follow-up note.
- If lexical retrieval requires a durable index or dependency, defer it to a separate milestone.
- If ANN tuning risks recall under filters, preserve current exact fallback behavior and document the finding.
