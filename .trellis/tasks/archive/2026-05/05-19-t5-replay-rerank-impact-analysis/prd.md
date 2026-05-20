# T5 replay and rerank impact analysis

## Goal

Ship the first real eval-as-driver replay tool promised by Architecture v2 C9.
The tool reads persisted `QueryPlan` rows from per-KB SQLite (`query_plans.db`),
replays them against a selected IndexGeneration, optionally compares against a
baseline generation, and reports retrieval/rerank impact metrics in JSON or
Markdown.

This replaces the current ad-hoc T1 replay script's role for architecture-level
gating. The existing `scripts/replay_against_generation.py` is feedback-jsonl +
lexical-only; T5 must use the QueryPlan substrate created by T2 and the
`rerank_json` metadata created by T3.

## User Value

- Operators can evaluate a shadow generation against real persisted retrieval
  traffic before swapping it active.
- Retrieval/ranking changes get a concrete replay gate instead of relying only
  on synthetic fixtures.
- Reranker rollout can be measured from plan logs: vendor use, cache hit/miss,
  fallback/skipped reasons, latency, and observed ordering impact.

## Confirmed Facts

- Architecture v2 C9 defines the desired CLI shape:
  `trellis-rag-eval replay --kb <kb_name> --generation g2 [--baseline g1] [--filter ...] [--metrics ...] [--output-format json|markdown]`.
- T2 ships `src/tagmemorag/queryplan/plan_log.py` with per-KB SQLite at
  `{data_dir}/{kb}/query_plans.db` and a `plans` table containing
  `query_rewrites_masked_json`, `filters_json`, `strategy_json`, `budget_json`,
  `served_by_generation`, `served_by_build_id`, `cache_status`,
  `evidence_ids_json`, `latency_ms_observed`, `warnings_json`, and
  `rerank_json`.
- T2 intentionally does not persist raw query separately; replay should use
  the first persisted masked rewrite. Current masking defaults to passthrough,
  but stricter future masking may make some rows less useful for replay.
- Private KBs are not persisted and therefore are out of scope for replay.
- T3 writes `rerank_json` from `/retrieve` when reranker is active, including
  vendor used, calibrator, latency, top_n returned, truncated count, cache
  status, and warnings.
- Existing `scripts/replay_against_generation.py` is explicitly labelled a
  minimal T1 tool, reads `feedback.jsonl`, and uses cheap lexical overlap rather
  than the actual search stack.
- Existing eval code already computes ranking metrics for synthetic suites, but
  plan-log replay needs its own QueryPlan row loader and generation-targeted
  search execution.

## Requirements

- Add a T5 replay CLI that can be invoked in the spirit of
  `trellis-rag-eval replay`.
- Read replay rows from `query_plans.db`, not `feedback.jsonl`.
- Support selecting a target generation and optional baseline generation.
- Reconstruct replay inputs from persisted plan data:
  - query from `query_rewrites_masked_json[0]`
  - filters from `filters_json`
  - budget/top-k hints from `budget_json` where available
  - intent/cache/rerank metadata for slicing and reporting
- Execute replay using the real local retrieval stack against the selected
  generation artifacts, not lexical overlap only.
- Produce deterministic machine-readable JSON output.
- Produce Markdown output suitable for an operator or PR summary.
- Support an MVP filter language covering at least:
  - `intent=<value>`
  - `created_after=<ISO date/time or YYYY-MM-DD>`
  - `created_before=<ISO date/time or YYYY-MM-DD>`
  - `cache_status=<hit|miss|disabled>`
  - `rerank_vendor=<vendor_used value>`
  - `limit=<N>` or equivalent CLI limit
- Compute baseline-vs-target deltas for agreed MVP metrics.
- Summarize reranker impact from existing `rerank_json` even when replay is run
  without making any external reranker call.
- Never make external reranker/vendor calls by default during replay.
- Preserve the old T1 script behavior until a replacement path is proven; do
  not silently break `tests/unit/test_replay_against_generation.py`.

## MVP Metrics

- `queries_replayed`
- `any_hit_rate`: at least one result returned for the replayed query
- `evidence_overlap_at_k`: overlap between stored evidence ids/chunk ids and
  replayed top-k evidence/chunk ids when stored evidence is available
- `top1_stability`: whether top-1 chunk/evidence stays the same versus stored
  plan result or baseline generation when comparable
- `latency_ms_p50` / `latency_ms_p95` observed during replay
- `rerank_fallback_rate`: from persisted `rerank_json.warnings` and
  `vendor_used="noop"`
- `rerank_cache_hit_rate`: from persisted `rerank_json.cache_status`

## Out of Scope

- LLM-as-judge faithfulness scoring.
- `/answer` quality evaluation.
- Real traffic splitting.
- Persisting new replay reports into a database.
- Replaying private KBs.
- Reconstructing unmasked raw queries when masking rules have removed the
  necessary text.
- Calling external reranker vendors during replay by default.
- Replacing all existing synthetic eval suites.

## Decisions

### D1 Replay Scope: offline retrieval replay + rerank log analysis

T5 MVP does not re-execute external reranker calls. It replays local retrieval
against selected generation artifacts and summarizes historical reranker impact
from persisted `rerank_json`.

Reasoning: this creates a safe generation-swap gate and reranker rollout report
without vendor cost, credentials, network variance, or nondeterminism. A future
task may add an explicit opt-in live reranker replay mode once the offline
contract is stable.

## Open Questions

- None blocking after D1. Detail-level design choices are captured in
  `design.md`.

## Acceptance Criteria

- [ ] QueryPlan SQLite reader loads persisted plans from `{kb}/query_plans.db`
      and safely skips malformed/unreplayable rows with warnings.
- [ ] Replay CLI supports target generation, optional baseline generation,
      output format (`json|markdown`), limit, and the MVP filters listed above.
- [ ] Replay uses selected generation artifacts instead of whichever generation
      is active in app memory.
- [ ] JSON report contains target metrics, optional baseline metrics, deltas,
      row counts, skipped-row reasons, filter summary, and rerank summary.
- [ ] Markdown report renders the same key numbers in a readable operator
      summary.
- [ ] Existing T1 `scripts/replay_against_generation.py` tests remain green or
      are migrated with backward-compatible behavior preserved.
- [ ] Unit tests cover plan-log fixture loading, filters, malformed JSON,
      missing DB/index artifacts, target-only replay, baseline delta replay,
      markdown output, and rerank summary parsing.
- [ ] Architecture C9 status or notes are updated to reflect the shipped T5
      replay tool.
- [ ] Final validation includes the focused T5 tests plus `git diff --check`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
