# implement.md - M25 Hybrid Lexical Retrieval for Fault Codes and Model Terms

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review current M23 experiment evidence and existing product-manual eval cases.
- [x] Add harder lexical-sensitive eval cases to `tests/fixtures/eval/product_manuals.jsonl` or a focused companion suite.
- [x] Run and record M25 baseline exact-local eval results in `research/experiments.md`.
- [x] Decide whether baseline exposes enough weakness to justify production retrieval changes.
- [ ] If no production change is justified:
  - [ ] Document the no-change decision with metrics.
  - [ ] Add only useful eval cases/docs if they improve future coverage.
- [x] If production change is justified:
  - [x] Add `SearchConfig` lexical settings.
  - [x] Add `src/tagmemorag/lexical_search.py` with token extraction and node scoring.
  - [x] Add unit tests for token normalization, code/model variants, CJK substring handling, and score caps.
  - [x] Wire lexical scoring into `execute_search()`.
  - [x] Extend `wave_search()` with disabled-mode-equivalent lexical parameters.
  - [x] Ensure lexical candidates respect filters and KB isolation.
  - [x] Ensure Qdrant ANN remains candidate-generation-only and unions lexical candidates safely.
  - [x] Update search cache suffix for lexical settings.
  - [x] Update debug metadata with low-cardinality lexical counts only.
  - [x] Update eval config snapshots if new settings should be recorded.
- [x] Add focused API/CLI/cache tests for lexical-enabled and lexical-disabled behavior.
- [x] Update README with hybrid lexical behavior, config, and eval commands.
- [x] Update backend specs if lexical behavior becomes a durable search contract.

## Suggested Implementation Order

1. **Eval First**
   - Add hard exact-token cases.
   - Run baseline with current code.
   - Save results to `research/experiments.md`.

2. **Lexical Helper**
   - Implement token extraction and node scoring as a pure module.
   - Test without touching API or WAVE code.

3. **Search Runtime Wiring**
   - Add config.
   - Compute lexical candidates inside `execute_search()`.
   - Keep disabled mode byte-for-behavior equivalent where tests can observe it.

4. **WAVE Integration**
   - Add lexical source seeding and bounded score hints.
   - Preserve deterministic ordering and aggregate semantics.

5. **ANN / Cache / Debug**
   - Union lexical candidates with ANN candidates.
   - Update cache suffix.
   - Add safe debug fields.

6. **Evidence And Docs**
   - Re-run M23/M25 evals.
   - Document accepted/rejected behavior.

## Validation

Baseline / experiment commands:

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

Focused tests:

```bash
uv run pytest tests/unit/test_graph_wave.py tests/unit/test_eval_runner.py tests/unit/test_cli.py tests/unit/test_api.py -q
uv run pytest tests/unit/test_cache.py tests/unit/test_config_env.py -q
uv run pytest tests/e2e/test_eval_cli.py -q
```

Qdrant/ANN regression checks if ANN candidate behavior changes:

```bash
uv run pytest tests/unit/test_manual_library.py tests/unit/test_storage_state.py tests/unit/test_api.py -q
uv run pytest -q -k 'qdrant or ann' tests/unit tests/e2e
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm new eval cases actually represent realistic product-manual queries.
- Confirm any ranking change has before/after metrics.
- Confirm default enablement is justified; otherwise keep lexical disabled or candidate-limited.
- Confirm exact-local disabled mode matches current behavior.
- Confirm final ranking remains local WAVE-RAG.
- Confirm ANN scores do not become authoritative.
- Confirm filters, anchors, cache keys, auth, and KB isolation are preserved.
- Confirm debug metadata does not leak query tokens, source text, vectors, candidate IDs, or full paths.

## Rollback Points

- If hard eval cases pass without lexical changes, stop after documenting evidence.
- If lexical scoring helps one case but regresses M23 aggregate metrics, leave it config-disabled and document a follow-up.
- If source seeding is too invasive, fall back to candidate inclusion plus bounded post-propagation boost.
- If scan latency is unacceptable on larger graphs, defer durable lexical indexing to a separate task.

## Known Edge Cases To Test

- `E21`, `E-21`, and `E 21` query variants.
- Model IDs with mixed letters/numbers, such as `HR6FDFF701SW`.
- Short CJK terms like `童锁`, `排水泵`, `冷冻室`.
- Query contains a model number from one manual and generic symptom words from another.
- Filtered search with lexical matches outside the filter scope.
- ANN enabled but ANN misses the exact-code chunk.
- Empty query or query with only ignored tokens.
- No-sidecar KB where metadata fields are unavailable.
