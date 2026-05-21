# C5 Budget and Fallback — Technical Design

## 1. Module Boundary

Touched code:

- `src/tagmemorag/agentic/driver.py`
- `tests/unit/test_agentic_driver_loop.py`
- `tests/unit/test_agentic_replay_verdict.py` if needed

Forbidden:

- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/production_provider_verify.py`
- `src/tagmemorag/reranker/**`
- `src/tagmemorag/answer/openai_compatible.py`

## 2. Unified Fallback

Add an internal helper:

```python
def _terminate_with_fallback(
    state: AgentState,
    reason: str,
    *,
    plan_log: PlanLog | None = None,
    record_step: bool = True,
) -> AgentRunResult
```

Behavior:

- If `classic_fallback_answer` is missing, raise
  `RuntimeError("agentic fallback unavailable: <reason>")`.
- If `record_step` and `plan_log` and `plan.persist`, append:

```python
StepRecord(
  tool="fallback",
  args={},
  observation=ToolObservation(payload={
    "reason": reason,
    "history_len": len(state.history),
  }),
  grade=GradeOutcome(signal="no_signal", reason=reason),
  decision_source="rule",
  rationale=f"fallback:{reason}",
)
```

- Return `AgentRunResult(answer=classic_fallback, fallback_reason=reason)`.

No raw query, answer text, citations, snippets, candidate ids, or provider
payloads are stored in the fallback step.

## 3. Private-KB Guard

At the top of `run_agent`, before router preflight:

```python
if not plan.persist:
    return _terminate_with_fallback(
        state,
        "private_kb_classic",
        plan_log=None,
        record_step=False,
    )
```

Private KBs should not write agentic `plan_steps`.

## 4. Budget Checks

Existing `_fallback_if_exhausted` should accept `plan_log` and delegate to the
unified helper. Every pre-tool budget check goes through this path.

`_call_tool` remains defensive and can still raise if a caller bypasses the
pre-check without fallback.

## 5. Replay

Fallback steps use the same deterministic rule-step shape, so C1 replay
helpers already handle them. Add a unit assertion if coverage is missing.

## 6. Compatibility

- Successful paths do not write fallback steps.
- `router=None` and no budget exhaustion preserve current behavior.
- `plan.persist=True` is the default, so private guard only affects explicit
  private/sensitive plans.
