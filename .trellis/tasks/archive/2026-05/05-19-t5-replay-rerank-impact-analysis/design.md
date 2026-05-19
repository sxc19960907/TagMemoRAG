# T5 replay and rerank impact analysis — Design

## 1. Scope

T5 ships a deterministic offline replay path for persisted QueryPlans:

```text
query_plans.db row
  -> ReplayPlan
  -> selected generation GraphState
  -> execute_search()
  -> ReplayCaseResult
  -> ReplayReport JSON / Markdown
```

The MVP is retrieval-only replay plus historical rerank log analysis. It does
not call external reranker vendors and does not evaluate generated answers.

## 2. Module Layout

New package:

```text
src/tagmemorag/replay/
  __init__.py
  cli.py
  filters.py
  generation.py
  loader.py
  metrics.py
  models.py
  report.py
  runner.py
```

Rationale:

- `replay/loader.py` owns SQLite row reading and JSON parsing.
- `replay/generation.py` owns loading generation-specific graph/vector/anchor
  artifacts into a temporary `GraphState`.
- `replay/runner.py` owns query embedding + `execute_search`.
- `replay/metrics.py` owns per-case and aggregate calculations.
- `replay/report.py` owns JSON/Markdown rendering.
- `replay/cli.py` is the command entry point and must not contain business
  logic beyond argparse wiring.

Optional compatibility wrapper:

```text
scripts/trellis_rag_eval.py
```

This script bootstraps `src/` on `sys.path` and forwards to
`tagmemorag.replay.cli:main`. The old `scripts/replay_against_generation.py`
stays untouched for T1 compatibility.

## 3. CLI Contract

MVP command:

```bash
uv run python scripts/trellis_rag_eval.py replay \
  --kb default \
  --generation 2 \
  --baseline 1 \
  --config config.yaml \
  --filter intent=text_answer \
  --filter created_after=2026-05-01 \
  --filter cache_status=miss \
  --metrics any_hit_rate,evidence_overlap_at_k,top1_stability,latency_ms_p50,latency_ms_p95 \
  --limit 100 \
  --output-format json
```

Generation ids accept `2`, `g2`, `active`, and `shadow`.

Exit codes:

- `0`: completed with no regression according to selected comparison rules.
- `2`: invalid input or missing required artifacts.
- `3`: completed and regression threshold failed.

Regression threshold for MVP: when baseline is present, exit `3` only if
`any_hit_rate_delta < 0`. Other deltas are informational until calibrated.

## 4. Data Contracts

### ReplayPlan

Dataclass fields:

- `plan_id: str`
- `kb_name: str`
- `query: str`
- `created_at: str`
- `intent: str`
- `filters: dict[str, Any]`
- `budget: dict[str, Any]`
- `stored_evidence_ids: tuple[str, ...]`
- `cache_status: str`
- `rerank: dict[str, Any] | None`
- `warnings: tuple[str, ...]`

Rows are skipped when:

- `query_rewrites_masked_json` is missing, malformed, empty, or first rewrite is
  blank.
- `filters_json` or `budget_json` is malformed.
- `intent` does not match the caller filter.

Malformed rows are counted in `skipped_rows` with a reason; they do not abort the
whole replay.

### ReplayCaseResult

Dataclass fields:

- `plan_id`
- `query_hash` is intentionally not needed once the row is loaded.
- `query_replayed: bool`
- `generation`
- `result_count`
- `top_chunk_id`
- `top_evidence_id`
- `chunk_ids`
- `evidence_ids`
- `latency_ms`
- `warnings`
- `error`

### ReplayReport

Top-level JSON shape:

```json
{
  "schema_version": "replay_report.v1",
  "kb": "default",
  "filters": {},
  "metrics_requested": [],
  "row_counts": {
    "loaded": 10,
    "selected": 8,
    "skipped": 2,
    "replayed": 8
  },
  "target": {
    "generation": 2,
    "metrics": {},
    "cases": []
  },
  "baseline": {
    "generation": 1,
    "metrics": {},
    "cases": []
  },
  "deltas": {},
  "rerank_summary": {},
  "skipped_rows": []
}
```

`cases` are included by default for JSON because early T5 users need debugging
detail. A future `--summary-only` flag can trim case rows.

## 5. Plan-Log Loading

`ReplayPlanLoader` opens:

```text
Path(settings.storage.data_dir) / kb_name / "query_plans.db"
```

It uses stdlib `sqlite3`, checks `PRAGMA user_version`, and refuses future
schema versions greater than `PLAN_LOG_SCHEMA_VERSION`.

SQL selection is intentionally simple in MVP:

- read rows ordered by `created_at ASC`
- apply cheap SQL filters for `intent`, `cache_status`, and created range
- apply rerank vendor and malformed-row checks in Python
- apply `limit` after filters

Reasoning: filter expressiveness is still small, and Python-side parsing keeps
SQLite schema coupling contained.

## 6. Filter Language

`--filter key=value` supports:

- `intent`
- `created_after`
- `created_before`
- `cache_status`
- `rerank_vendor`

`--limit N` is a first-class argument, not a filter key.

Validation happens in `filters.py`. Unknown keys are invalid input (exit `2`).
Date values accept `YYYY-MM-DD` or ISO-8601 UTC-ish strings already used by
plan log (`YYYY-MM-DDTHH:MM:SSZ`).

## 7. Generation Loading

`generation.py` resolves a generation selector:

- integer / `gN` -> that generation
- `active` -> `index.json.active_generation`
- `shadow` -> `index.json.shadow_generation`

It loads artifacts from `KbPaths(kb_name, settings, generation=N)`:

- `graph.json`
- `vectors.npz`
- `anchors.json`
- `meta.json`

It builds a temporary `GraphState` directly. It does not mutate `AppState` and
does not swap active generations.

For Qdrant-backed configs, MVP should fail with a clear unsupported message
unless local vectors are present. Reasoning: replay must be deterministic and
offline; online Qdrant generation replay needs a separate contract around
collection selection and availability.

## 8. Replay Execution

For each plan:

1. Encode `ReplayPlan.query` with `create_embedder(...)` from loaded settings.
2. Resolve search params from settings defaults and persisted budget:
   - `top_k = budget.max_evidence` if present, else `settings.search.top_k`
   - `source_k`, `steps`, `decay`, `amplitude_cutoff`, `aggregate` from settings
3. Call `execute_search(...)` with:
   - selected generation `GraphState`
   - query text
   - persisted filters
   - no ghost tags or core tags in MVP because QueryPlan does not persist them
4. Build a lightweight retrieve-shaped evidence list with
   `build_retrieve_response(...)` so evidence ids/chunk ids are computed through
   the same code path as `/retrieve`.

No plan log writes occur during replay.

## 9. Metrics

MVP aggregate metrics:

- `queries_replayed`
- `any_hit_rate`
- `evidence_overlap_at_k`
- `top1_stability`
- `latency_ms_p50`
- `latency_ms_p95`

Definitions:

- `any_hit_rate`: cases with `result_count > 0` divided by replayed cases.
- `evidence_overlap_at_k`: average Jaccard overlap between stored
  `evidence_ids_json` and replayed evidence ids. If stored evidence ids are
  absent for a case, skip that case for this metric and report
  `evidence_overlap_cases`.
- `top1_stability`: target-only mode compares replayed top evidence id to the
  stored top evidence id when present. Baseline comparison mode compares target
  top chunk id to baseline top chunk id for the same plan.
- `latency_ms_p50/p95`: percentile over successful replay case latencies.

Deltas:

- numeric target minus baseline for shared metric names.
- missing baseline metrics are omitted from `deltas`.

## 10. Rerank Summary

Rerank summary uses persisted `ReplayPlan.rerank` only.

Fields:

- `plans_with_rerank`
- `vendor_counts`
- `fallback_count`
- `fallback_rate`
- `cache_counts`
- `cache_hit_rate`
- `warning_counts`
- `latency_ms_p50`
- `latency_ms_p95`
- `truncated_total`

Fallback rule:

- `vendor_used == "noop"` counts as fallback.
- Any warning beginning with `reranker_fallback` also counts as fallback.

This summary is independent of target/baseline replay because D1 forbids live
external reranker calls in MVP.

## 11. Markdown Output

Markdown report contains:

- title with KB and generation comparison
- row counts
- target metrics
- baseline metrics and deltas when present
- rerank summary
- skipped-row reason counts
- regression verdict

No raw query text is printed in Markdown by default. JSON may include per-case
plan ids and metrics but should also avoid raw query text in the top-level report
unless a future debug flag explicitly asks for it.

## 12. Compatibility

`scripts/replay_against_generation.py` remains as-is. T5 adds a new command path
instead of changing its semantics. Existing unit tests for the old script must
continue passing.

If the package later gains console scripts in `pyproject.toml`, they can point
to `tagmemorag.replay.cli:main` without changing the module design.

## 13. Failure Handling

- Missing `query_plans.db`: exit `2` with JSON error in JSON mode.
- Missing `index.json`: exit `2`.
- Unknown generation selector: exit `2`.
- Missing generation artifacts: exit `2`.
- Malformed individual rows: skip and report.
- Per-case replay exception: record case error, continue, count as not replayed
  for metric denominators.

## 14. Testing Strategy

Focused tests:

- filter parser
- SQLite plan fixture loading
- malformed JSON row skipping
- missing DB/index/generation errors
- generation selector resolution
- target-only replay
- baseline replay + delta
- Markdown output
- rerank summary parsing
- old T1 script tests still green

Fixtures should use hashing embedder and local NPZ vectors; no network.

## 15. Rollback

T5 is additive:

- new `src/tagmemorag/replay/` package
- new wrapper script
- tests
- architecture doc status/note update

Reverting the T5 files restores previous behavior. No storage migrations are
introduced.
