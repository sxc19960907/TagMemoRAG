# implement.md - M20 Retrieval Quality Expansion

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Review eval dataset, runner, matching, metrics, report, CLI eval command, managed-library rebuild helpers, and Qdrant fake-client patterns.
- [ ] Create expanded product-manual fixture directory with small synthetic manuals and metadata sidecars.
- [ ] Add `tests/fixtures/eval/product_manuals.jsonl` with semantic, fault-code, metadata/tag, anchor, ANN, and incremental-rebuild oriented cases.
- [ ] Update `run_eval()` to use `execute_search()` instead of direct `wave_search()`.
- [ ] Preserve existing coffee suite report behavior and CLI output.
- [ ] Add optional low-cardinality search execution fields to case reports if useful for ANN assertions.
- [ ] Add/adjust tests for eval suite loading and report generation using the expanded suite.
- [ ] Add a focused ANN eval test with `FakeQdrantClient` proving ANN preselection preserves an expected final result.
- [ ] Add a focused managed-library incremental rebuild followed by eval test.
- [ ] Keep default tests offline and deterministic with hashing embedder.
- [ ] Update README/docs with expanded eval suite commands and intended usage.
- [ ] Verify no eval/report/log output adds vectors, secrets, candidate id lists, or machine-specific absolute paths beyond explicit CLI input paths.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_eval_dataset.py tests/unit/test_eval_matching.py tests/unit/test_eval_metrics.py tests/unit/test_eval_runner.py tests/e2e/test_eval_cli.py -q
```

Search/Qdrant/manual-library focused tests:

```bash
uv run pytest tests/unit/test_api.py tests/unit/test_cli.py tests/unit/test_manual_library.py tests/unit/test_storage_state.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

Manual smoke command:

```bash
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config <hashing-config> \
  --eval-data-dir .tmp/eval-m20 \
  --output .tmp/eval-m20/report.json
```

## Review Gates

- Confirm expanded fixtures are synthetic, concise, and deterministic.
- Confirm eval runner uses the same execution semantics as API/CLI search.
- Confirm new report fields, if any, are additive and low-cardinality.
- Confirm ANN coverage uses fake Qdrant only and does not require network access.
- Confirm incremental rebuild eval proves post-change retrieval behavior.
- Confirm M20 does not tune ranking constants without report evidence and explicit rationale.

## Rollback Points

- If expanded fixture thresholds are flaky, lower per-case thresholds or split unstable cases into a non-default suite.
- If migrating `run_eval()` to `execute_search()` causes compatibility churn, introduce a narrow helper and preserve old report shape before adding ANN assertions.
- If incremental rebuild eval becomes too slow for default tests, keep a smaller default incremental smoke and move the broader scenario behind a slower marker/follow-up.
