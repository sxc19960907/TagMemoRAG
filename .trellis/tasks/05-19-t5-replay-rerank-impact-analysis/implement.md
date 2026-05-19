# T5 replay and rerank impact analysis — Implementation Checklist

6 slices. Each slice should leave tests green for the files it touches.

## Pre-flight

- [x] Active task is `.trellis/tasks/05-19-t5-replay-rerank-impact-analysis`.
- [x] Re-read `prd.md` D1 and `design.md`.
- [x] Read backend architecture C9, directory structure, database guidelines,
      and quality guidelines.
- [x] Confirm old T1 replay tests are passing before changing replay code:
      `uv run pytest tests/unit/test_replay_against_generation.py -q`.

## Slice 0 — Replay package contracts + filter parser

- [x] Create `src/tagmemorag/replay/__init__.py`.
- [x] Add `models.py` dataclasses:
      `ReplayPlan`, `ReplayCaseResult`, `ReplayRunMetrics`,
      `ReplayReport`.
- [x] Add `filters.py`:
      `ReplayFilters`, `parse_filter_args`, date normalization, validation.
- [x] Tests:
      `tests/unit/test_replay_filters.py` for valid filters, invalid keys,
      invalid dates, multiple filters, and limit handled outside filter parser.
- [ ] Commit target:
      `feat(replay): T5 Slice 0 — replay contracts and filters`.

## Slice 1 — QueryPlan SQLite loader

- [x] Add `loader.py` with `ReplayPlanLoader`.
- [x] Read `{settings.storage.data_dir}/{kb}/query_plans.db`.
- [x] Check `PRAGMA user_version` against `PLAN_LOG_SCHEMA_VERSION`.
- [x] Load rows ordered by `created_at ASC`.
- [x] Apply SQL filters for intent/cache/created range.
- [x] Parse JSON columns into `ReplayPlan`.
- [x] Skip malformed/unreplayable rows with structured skip reasons.
- [x] Apply `rerank_vendor` filter in Python.
- [x] Tests:
      `tests/unit/test_replay_loader.py` with fixture DB covering happy path,
      malformed rewrite JSON, malformed budget/filter JSON, unknown schema,
      missing DB, created range, cache status, intent, rerank vendor, and limit.
- [ ] Commit target:
      `feat(replay): T5 Slice 1 — load QueryPlans from SQLite`.

## Slice 2 — Generation loader

- [x] Add `generation.py` with:
      `resolve_generation_selector(kb_name, settings, selector)`.
- [x] Support selectors: `active`, `shadow`, `N`, `gN`.
- [x] Add `load_generation_state(kb_name, settings, generation)`.
- [x] Load graph, vectors, anchors, and meta through generation-aware paths.
- [x] Build temporary `GraphState` without mutating `AppState`.
- [x] Return clear errors for missing `index.json`, missing generation, retired
      or unavailable generation artifacts, and unsupported Qdrant-only replay.
- [x] Tests:
      `tests/unit/test_replay_generation.py` for selectors and artifact
      loading using hashing embedder fixtures.
- [ ] Commit target:
      `feat(replay): T5 Slice 2 — load selected IndexGeneration artifacts`.

## Slice 3 — Runner + metrics

- [x] Add `runner.py` to execute replay plans against a loaded generation.
- [x] Use `create_embedder` from settings.
- [x] Call `execute_search` with persisted filters and settings defaults.
- [x] Use `build_retrieve_response` to derive evidence ids/chunk ids.
- [x] Do not call reranker dispatcher.
- [x] Add `metrics.py`:
      aggregate any-hit, evidence overlap, top1 stability, latency p50/p95,
      deltas, and rerank summary.
- [x] Tests:
      `tests/unit/test_replay_runner.py` for target-only replay, per-case
      errors, and no external reranker call path.
- [x] Tests:
      `tests/unit/test_replay_metrics.py` for aggregate metrics, delta
      calculation, empty input, skipped evidence-overlap cases, and rerank
      fallback/cache summaries.
- [ ] Commit target:
      `feat(replay): T5 Slice 3 — execute replay and compute metrics`.

## Slice 4 — CLI + reports

- [x] Add `report.py` for deterministic JSON dict rendering and Markdown.
- [x] Add `cli.py` with subcommand `replay`.
- [x] Add wrapper script `scripts/trellis_rag_eval.py`.
- [x] CLI supports:
      `--kb`, `--generation`, `--baseline`, `--config`, `--filter`,
      `--metrics`, `--limit`, `--output-format`.
- [x] Exit code `2` for invalid input / missing artifacts.
- [x] Exit code `3` when baseline exists and any-hit regression is negative.
- [x] Tests:
      `tests/unit/test_replay_cli.py` using subprocess for JSON, Markdown,
      missing artifacts, baseline delta, and regression exit code.
- [x] Existing tests:
      `uv run pytest tests/unit/test_replay_against_generation.py -q`.
- [ ] Commit target:
      `feat(replay): T5 Slice 4 — add trellis-rag-eval replay CLI`.

## Slice 5 — Architecture docs + final validation

- [x] Update `.trellis/spec/backend/architecture.md` C9 status from 🚧 to ✅
      or add a shipped note if retaining future-work nuance.
- [x] Update Follow-up Execution Roadmap row for T5 to shipped.
- [x] Optional memory/spec note only if implementation reveals a reusable
      convention not already in architecture.
- [x] Validation:

```bash
uv run pytest tests/unit/test_replay_filters.py \
  tests/unit/test_replay_loader.py \
  tests/unit/test_replay_generation.py \
  tests/unit/test_replay_runner.py \
  tests/unit/test_replay_metrics.py \
  tests/unit/test_replay_cli.py \
  tests/unit/test_replay_against_generation.py -q
git diff --check
```

- [x] If focused tests pass, run broader relevant suite:

```bash
uv run pytest tests/unit/test_queryplan_plan_log.py tests/unit/test_reranker_api_e2e.py -q
```

- [ ] Commit target:
      `docs(spec): T5 Slice 5 — mark eval replay tool shipped`.

## Review Gates

- [x] After Slice 1: verify loader never prints raw query text and handles
      malformed rows without aborting.
- [x] After Slice 3: verify no external reranker code path is invoked.
- [x] After Slice 4: run JSON CLI manually against a synthetic DB and inspect
      output shape.
- [ ] Before `task.py finish/archive`: run final validation and update journal.

## Rollback

T5 is additive. Revert the new replay package, wrapper script, tests, and
architecture doc update. No storage migration or runtime behavior change is
introduced.
