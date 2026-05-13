# design.md - M20 Retrieval Quality Expansion

## Scope

M20 expands retrieval quality measurement for TagMemoRAG. The implementation should produce a richer offline eval corpus and make the eval runner follow the same search execution semantics as the API/CLI path, especially for ANN preselection.

This task should not optimize ranking constants. If the expanded suite reveals quality problems, capture them in report output or a follow-up tuning task unless a small correctness fix is required for the suite to run.

## Current Flow

```text
tagmemorag eval run
  -> load JSONL eval cases
  -> build or load KB
  -> embed query
  -> wave_search(...)
  -> match expected results
  -> compute per-case and aggregate metrics
  -> print/write JSON report
```

Important gap: `run_eval()` currently calls `wave_search()` directly, so it bypasses `execute_search()` and cannot naturally evaluate Qdrant ANN preselection, ANN fallback, or future shared search execution diagnostics.

## Proposed Flow

```text
tagmemorag eval run
  -> load JSONL eval cases
  -> build or load KB
  -> embed query
  -> execute_search(...)
       -> exact local OR ANN preselection
       -> local WAVE-RAG ranking
  -> match expected results
  -> compute per-case and aggregate metrics
  -> include low-cardinality search execution metadata if useful
  -> print/write JSON report
```

The key technical contract is that eval uses the same search execution layer as API/CLI, while preserving the existing report contract for consumers.

## Fixture Design

Recommended layout:

```text
tests/fixtures/product_manuals/
  coffee/
    coffee_machine.md
    coffee_machine.metadata.json
  refrigerator/
    refrigerator_nrk6192.md
    refrigerator_nrk6192.metadata.json
  washer/
    washer_wm8.md
    washer_wm8.metadata.json
  air_conditioner/
    ac_ap12.md
    ac_ap12.metadata.json
  dishwasher/
    dishwasher_dw6.md
    dishwasher_dw6.metadata.json

tests/fixtures/eval/
  coffee.jsonl
  product_manuals.jsonl
```

Fixtures should be synthetic but realistic, concise, and designed around deterministic retrieval with `HashingEmbedder(dim=64)`.

Manual sidecars should cover safe metadata fields:

- `manual_id`
- `title`
- `source_file`
- `brand`
- `product_category`
- `product_model`
- `language`
- `tags`

Avoid absolute paths, secrets, or external vendor-private content.

## Eval Case Design

Use the existing JSONL case shape where possible:

```json
{
  "id": "fridge-temperature-zh",
  "kb_name": "default",
  "query": "冷藏室温度太高怎么调",
  "relevant": [
    {
      "source_file": "refrigerator_nrk6192.md",
      "header": "冷藏室温度",
      "text_contains": ["冷藏室", "温度"],
      "metadata": {"product_category": "fridge", "product_model": "NRK6192"}
    }
  ],
  "tags": ["fridge", "temperature"],
  "top_k_override": 10,
  "min_recall_at_k": 0.5,
  "min_mrr": 0.1
}
```

Case categories should include:

- `semantic`: symptom/task phrasing does not exactly match the header.
- `fault-code`: error code plus action.
- `metadata`: expected result has product/category/model/manual metadata.
- `tags`: expected result includes canonical tags or governance-resolved tags.
- `anchor`: expected result should move into top-k after an anchor is present.
- `ann`: ANN preselection should preserve a relevant result.
- `incremental`: changed manual content should be reflected after incremental rebuild and eval.

If a scenario needs setup beyond static JSONL, keep the JSONL case simple and put the scenario setup in a focused Python test.

## Runner Changes

### Shared Search Execution

Replace direct `wave_search()` calls inside `run_eval()` with `execute_search()`:

```python
execution = execute_search(
    state=state,
    query_vec=query_vec,
    settings=run_cfg,
    top_k=case_top_k,
    source_k=run_cfg.search.source_k,
    steps=run_cfg.search.steps,
    decay=run_cfg.search.decay,
    amplitude_cutoff=run_cfg.search.amplitude_cutoff,
    aggregate=run_cfg.search.aggregate,
    filters=case_filters,
)
results = execution.results
```

MVP can use empty filters unless `EvalCase` is extended with explicit filters. If filters are added, keep them structured and compatible with API filter normalization.

### Report Metadata

Preserve existing fields:

- `suite`
- `docs`
- `kb_names`
- `top_k`
- `thresholds`
- `summary`
- `cases`
- `config_snapshot`

Optional additive case-level fields may include:

- `search_strategy`
- `ann_candidate_count`
- `ann_fallback_reason`

Do not include query vectors, candidate ids, trace ids, search ids, secrets, or local absolute source paths not already provided by the user as CLI paths.

### ANN Test Strategy

Use `FakeQdrantClient` from existing tests and monkeypatch `QdrantVectorStore._create_client` in focused unit/e2e tests. Do not require live Qdrant.

ANN tests should verify:

- `vector_store.provider=qdrant`
- `search.ann_preselect_enabled=true`
- `execute_search()` path reports `ann_preselect_then_wave` where candidates are valid
- expected final WAVE-RAG results still match eval expectations

### Incremental Rebuild Test Strategy

Use the managed-library helpers or existing CLI/API patterns from M13/M15-era tests:

1. Create a small manual library.
2. Build the initial KB.
3. Run eval and assert old expected result.
4. Modify or replace one manual.
5. Run managed-library incremental rebuild.
6. Run eval with `--reuse-built-kb` or direct `run_eval()`.
7. Assert changed content is matched and report passes.

The test should stay local, hashing-embedder based, and small.

## Compatibility

- Existing eval JSONL suites remain valid.
- Existing coffee eval CLI behavior remains valid.
- Existing report consumers should continue to work because new fields are additive.
- Existing default config does not change.
- No new production dependencies should be added.

## Observability and Safety

- Eval report may include synthetic fixture text in `actual_top_k`, matching the existing report behavior.
- Do not add raw query text to logs or metrics beyond existing eval report case fields.
- Do not include vectors, secrets, API keys, Qdrant payload dumps, candidate id lists, or high-cardinality metric labels.
- Keep paths in fixtures relative. CLI report may still echo user-provided `--suite`/`--docs` paths as it does today.

## Rollout / Rollback

- Rollout is low risk because eval fixtures and tests are developer-facing.
- If runner migration to `execute_search()` causes unexpected broad failures, keep fixture expansion and isolate the runner change behind a small helper in `eval.runner`, then complete migration before marking M20 done.
- Rollback can remove the new suite/tests without affecting production search behavior.

## Open Questions

- Should `EvalCase` grow first-class `filters`, or should metadata/tag relevance remain expectation-only for M20?
  - MVP recommendation: only add filters if a concrete eval case needs filtered search behavior; otherwise avoid schema churn.
- Should report text snippets be truncated more aggressively for expanded fixtures?
  - MVP recommendation: keep the existing 500-character truncation unless report size becomes noisy.
- Should broad product-manual eval run in default e2e or a slower optional suite?
  - MVP recommendation: keep it in default tests if the hashing fixture remains fast; otherwise split a focused default smoke plus optional full command.
