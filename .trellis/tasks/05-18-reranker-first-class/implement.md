# T3 — Reranker first-class — Implementation Checklist

8 slices. Each independently reviewable; commit boundary at slice end.

## Pre-flight

- [ ] git tree clean.
- [ ] Active task = this one.
- [ ] Re-read prd.md D1–D7 + design.md § 1–12.
- [ ] Eval slice declaration: existing fixtures + 3 mocked SF responses (happy/429/5xx); new tests cover ≥6 of the 11 risks listed in design § 11.

## Slice 0 — Settings.reranker block

- [ ] Add `RerankerConfig` to `src/tagmemorag/config.py` per design § 8.
- [ ] Register `Settings.reranker: RerankerConfig` field.
- [ ] Tests: defaults round-trip, env override (TAGMEMORAG__RERANKER__*), yaml override.
- [ ] Commit: `feat(reranker): T3 Slice 0 — add RerankerConfig settings block`.

## Slice 1 — Reranker package + dataclasses + Protocol

- [ ] New module `src/tagmemorag/reranker/__init__.py` exporting public API.
- [ ] `src/tagmemorag/reranker/base.py`: `RerankDoc`, `RerankResultItem`, `RerankResult`, `RerankSpec`, `Reranker` Protocol.
- [ ] `src/tagmemorag/reranker/local_fallback.py`: `NoopReranker` (returns RerankResult with vendor_used="noop", candidates passthrough by score).
- [ ] Tests: dataclass JSON round-trip, NoopReranker passthrough preserves order.
- [ ] Commit: `feat(reranker): T3 Slice 1 — Protocol + dataclasses + NoopReranker`.

## Slice 2 — 4 Calibrators + CircuitBreaker

- [ ] `src/tagmemorag/reranker/calibration.py`: `Calibrator` Protocol + `MinMax`/`ZScore`/`Sigmoid`/`Identity` implementations + `build_calibrator(name)`.
- [ ] `src/tagmemorag/reranker/circuit_breaker.py`: `CircuitBreaker` (Lock-protected; threshold + cooldown).
- [ ] Tests: 4 calibrators × edge cases (empty/single/all-equal/normal); breaker open/cooldown/reset/concurrent calls smoke.
- [ ] Commit: `feat(reranker): T3 Slice 2 — calibrators + circuit breaker`.

## Slice 3 — RerankCache (LRU)

- [ ] `src/tagmemorag/reranker/cache.py`: `RerankCache` (OrderedDict + Lock).
- [ ] Tests: get/put roundtrip, LRU eviction, key isolation across (id/version/instruction/query/chunks), thread-safety smoke.
- [ ] Commit: `feat(reranker): T3 Slice 3 — LRU rerank cache`.

## Slice 4 — SF Qwen3 adapter

- [ ] `src/tagmemorag/reranker/siliconflow.py`: `SFQwen3Reranker` per design § 3.
- [ ] httpx-based POST; retry decision tree (HTTP 200 / 4xx / 429 / 5xx / timeout); pre-truncation; cleanup.
- [ ] Tests (mocked httpx): happy path; 429 → retry → success; persistent 5xx → vendor error; HTTP 4xx no retry; truncation surfaces truncated_chunk_ids; instruction included only when supports_instruction; budget_ms maps to httpx timeout.
- [ ] Commit: `feat(reranker): T3 Slice 4 — SF Qwen3-Reranker-0.6B adapter`.

## Slice 5 — Dispatcher

- [ ] `src/tagmemorag/reranker/dispatcher.py`: `RerankerDispatcher` per design § 4.
- [ ] ACL/disabled/tier-off short-circuit; budget pre-check; cache lookup; vendor call; calibrate-and-assemble; failure → noop fallback.
- [ ] Tests: each branch of the routing tree; cache hit/miss; vendor failure → noop; private KB short-circuit; budget too tight skips.
- [ ] Commit: `feat(reranker): T3 Slice 5 — dispatcher with tier routing + ACL gate + fallback`.

## Slice 6 — build_plan integration + RerankSpec on QueryPlan

- [ ] Update `src/tagmemorag/queryplan/planner.py:build_plan`: resolve `rerank_tier` per D6 rules (enabled flag + client override); set `Budget.rerank_candidates_n`; attach `RerankSpec` to `plan.rerank` when tier != "off".
- [ ] Update `Budget` dataclass to include `rerank_candidates_n: int = 0` (default 0 means "use request.top_k", set by build_plan only when rerank active).
- [ ] Tests: `enabled=False` forces tier=off; `enabled=True` + client unspecified uses default_tier; private KB still forces off; RerankSpec attached when active.
- [ ] Commit: `feat(reranker): T3 Slice 6 — RerankSpec attached on QueryPlan`.

## Slice 7 — Wire `/retrieve` to dispatcher

- [ ] In `_retrieve_impl`: when rerank_tier != "off", call `execute_search` with `top_k=Budget.rerank_candidates_n`; pass results to dispatcher; reorder; pass reordered results to `build_retrieve_response`.
- [ ] Add `rerank` field to plan_log update_result_async payload.
- [ ] Response includes warnings from rerank_outcome.
- [ ] Tests: `/retrieve` with rerank enabled returns plan_id; mocked SF returns reordered results; rerank field eventually appears in plan log; private KB never calls SF (verified via mock counter); vendor failure returns warnings + noop ordering.
- [ ] Commit: `feat(reranker): T3 Slice 7 — wire /retrieve pipeline to reranker dispatcher`.

## Slice 8 — architecture.md A3 ✅ + memory

- [ ] architecture.md A3 status 🚧 → ✅; add T3 shipped paragraph (analogous to T2 § A2).
- [ ] Appendix A SF Qwen3-Reranker-0.6B reference dated and confirmed.
- [ ] Memory: `t3-reranker-mechanism-key-points.md` (reference type) + optional `t3-implementation-lessons.md` if D8+ surfaced.
- [ ] MEMORY.md index updated.
- [ ] Commit: `docs(spec): T3 Slice 8 — architecture.md A3 ✅ + memory`.

## Final Validation

```bash
uv run pytest tests/unit -x --no-header -q --ignore=tests/unit/test_diag_realmanuals_eval.py
git diff --check
```

All green. Eval slice deltas reported in commit messages.

## Review Gates

- [ ] After Slice 4 (adapter): smoke test against tmp_path, ensure no real httpx call leaks.
- [ ] After Slice 7 (wireup): full unit + integration green.
- [ ] After Slice 8: user review before declaring complete.

## Rollback

Each slice independently revertable. Slice 0–6 are dormant unless dispatcher wired; reverting Slice 7 alone leaves the package present but unused — safe partial rollback.

## Out-of-band notes

- T3 ships `enabled=False`. Production launch is an ops yaml change after observation period. T3 task itself is "ready to flip" not "flipped".
- Cache key intentionally omits generation (D3 invariant). Future T1.5 (derivative isolation) does NOT require cache invalidation.
- T5 (replay tool) will read rerank_json from plan log and reconstruct rerank impact analyses.
