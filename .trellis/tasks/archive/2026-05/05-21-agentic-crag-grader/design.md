# C4 CRAG-lite Grader — Technical Design

## 1. Module Boundary

New file:

```text
src/tagmemorag/agentic/grader.py
```

Touched existing files:

- `src/tagmemorag/agentic/tools/grade.py`
- `src/tagmemorag/agentic/__init__.py`
- unit tests under `tests/unit/`

Forbidden:

- `src/tagmemorag/reranker/**`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/production_provider_verify.py`
- `src/tagmemorag/answer/openai_compatible.py`

## 2. Threshold Contract

```python
@dataclass(frozen=True)
class CragGradeThresholds:
    high_score: float = 0.6
    low_score: float = 0.2
    min_margin: float = 0.05
    min_depth: int = 1
```

C4 defaults live in code only. C6 can later map `AgenticConfig` fields onto
this dataclass.

## 3. Signal Derivation

Input: `RerankResult`.

Rules:

1. `cache_status == "skipped"` or `vendor_used == "noop"`:
   `GradeOutcome(signal="no_signal", reason="reranker_no_signal")`
2. no items:
   `GradeOutcome(signal="low", reason="empty_rerank_items")`
3. sort items by `calibrated_score` descending.
4. `top1_score = sorted_items[0].calibrated_score`
5. `margin = top1_score - top2_score` if top2 exists, else `top1_score`
6. if `top1_score >= high_score`, `margin >= min_margin`, and
   `len(items) >= min_depth`: signal `high`
7. if `top1_score <= low_score`: signal `low`
8. otherwise signal `inconclusive`

Depth is `len(items)` after sorting. Reason strings are stable and safe:
`high_confidence`, `low_score`, `inconclusive_margin`, etc.

## 4. GradeTool Integration

`GradeTool` gains optional `thresholds: CragGradeThresholds`.

Flow:

```text
dispatcher.rerank(plan, candidates, guard, query_text)
  -> RerankResult
  -> grade_rerank_result(result, thresholds)
  -> ToolObservation(payload={"grade": grade.to_dict(), "rerank": result.to_dict()})
```

Dispatcher call shape remains unchanged, preserving D6 cache-key invariants.

## 5. Driver Interaction

C3 already handles:

- `low` -> rewrite + retrieve
- `no_signal/high/inconclusive` -> final

C4 does not change driver logic unless tests reveal a bug. The integration
test should use real `GradeTool` with a fake dispatcher that returns low then
no_signal rerank results.

## 6. Replay

No schema changes. Computed grade is persisted in existing `signal`,
`top1_score`, `margin`, and `depth` columns.

## 7. Test Plan

- `tests/unit/test_agentic_grader.py`
  - high
  - high top1 but low margin -> inconclusive
  - low
  - no items -> low
  - noop/skipped -> no_signal
- `tests/unit/test_agentic_tools_stub.py`
  - GradeTool returns computed grade.
- `tests/unit/test_agentic_driver_loop.py`
  - fake dispatcher low then no_signal drives C3 loop.

Regression:

```bash
uv run pytest tests/unit/test_agentic_grader.py \
  tests/unit/test_agentic_tools_stub.py \
  tests/unit/test_agentic_driver_loop.py \
  tests/unit/test_agentic_router.py \
  tests/unit/test_agentic_replay_verdict.py \
  tests/unit/test_queryplan_plan_log.py \
  tests/unit/test_reranker_dispatcher_cache_key_invariant.py -q
uv run pytest -q
```
