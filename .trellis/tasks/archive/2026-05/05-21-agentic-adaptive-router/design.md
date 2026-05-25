# C2 Adaptive Router — Technical Design

## 1. Module Boundary

New file:

```text
src/tagmemorag/agentic/router.py
```

Touched C1 files:

- `src/tagmemorag/agentic/__init__.py` — export router contracts.
- `src/tagmemorag/agentic/driver.py` — optional router preflight.
- `src/tagmemorag/agentic/state.py` only if route step serialization needs a
  helper; prefer using existing `StepRecord` and `ToolObservation`.

Forbidden in C2:

- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/reranker/**`
- `src/tagmemorag/answer/openai_compatible.py`

## 2. Router Contracts

```python
RouteKind = Literal["no_retrieval", "single_shot", "multi_hop"]

@dataclass(frozen=True)
class RouteDecision:
    route: RouteKind
    confidence: float
    reason: str
    features: dict[str, bool | int | float | str]

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteDecision": ...

class AdaptiveRouter(Protocol):
    def route(self, *, plan: QueryPlan, query_text: str) -> RouteDecision: ...
```

`features` must be safe operational metadata only: booleans/counters such as
`has_compare_marker`, `has_step_marker`, `query_token_count`, or
`planner_out_of_scope`. Do not store raw query text or retrieved snippets in
the route observation.

## 3. Rule-Based Router

`RuleBasedAdaptiveRouter` is conservative and deterministic.

Classification order:

1. `no_retrieval`
   - `plan.intent == Intent.OUT_OF_SCOPE`
   - normalized query is empty
   - greeting-only or acknowledgement-only query
2. `multi_hop`
   - query contains comparison markers: `compare`, `difference`, `versus`,
     `vs`, `better`, `哪个更`, `区别`, `对比`
   - query contains step/dependency markers: `first`, `then`, `after`,
     `before`, `based on`, `根据...再`, `先...再`
   - query names multiple manuals/models/categories using safe metadata
     signals available on the plan
3. fallback: `single_shot`

No LLM call is allowed in C2. A future LLM router can implement
`AdaptiveRouter` without changing driver call sites.

## 4. Driver Integration

Add optional parameters to `run_agent`:

```python
router: AdaptiveRouter | None = None
```

Preflight flow:

```text
if router is None:
    keep C1 behavior

decision = router.route(plan=plan, query_text=initial_query)
append route StepRecord if plan_log exists

if decision.route == "single_shot":
    return classic_fallback exactly
if decision.route == "no_retrieval":
    return classic_fallback exactly for C2
if decision.route == "multi_hop":
    continue into C1 retrieve -> grade -> final behavior
```

C2 intentionally maps `no_retrieval` to fallback rather than inventing a
provider answer. A dedicated no-retrieval final response can be designed when
C6 owns the public API contract.

Route step record:

```python
StepRecord(
    step_idx=0,
    tool="route",
    args={},
    observation=ToolObservation(payload={"route": decision.to_dict()}),
    grade=GradeOutcome(signal="no_signal", reason="route_preflight"),
    decision_source="rule",
    rationale=decision.reason,
    ts=now_iso_utc(),
)
```

If the route short-circuits, no retrieve/grade/final tools are called.
If the route is `multi_hop`, this route record occupies `step_idx=0` and the
existing C1 retrieve step naturally starts at `step_idx=1`.

## 5. Replay

C1 replay already compares stored deterministic rule steps. A route step uses
the same row shape, so no new table or replay schema is needed. Add unit
coverage that `replay_steps` treats a stored route step as `overall="match"`.

## 6. Compatibility

- Default behavior is unchanged because `router=None` preserves the C1 driver
  path.
- C2 does not add config fields, request fields, or CLI flags.
- Route observation does not store raw query text, snippets, vectors, or
  provider payloads.
- `BudgetGuard` is not consumed by a short-circuit route step; the route is a
  control decision, not an external tool call. C5 may add route-cost accounting
  later if needed.

## 7. Test Plan

Unit tests:

- `test_rule_router_single_shot_for_agentic_simple_passthrough`
- `test_rule_router_multi_hop_markers`
- `test_rule_router_no_retrieval_empty_greeting_out_of_scope`
- `test_driver_single_shot_returns_classic_fallback_without_tool_calls`
- `test_driver_single_shot_writes_route_step`
- `test_replay_route_step_matches`

Regression checks:

- Existing C1 agentic unit test set.
- Full `uv run pytest -q`.
- `git diff --name-only HEAD -- src/tagmemorag/api.py src/tagmemorag/cli.py src/tagmemorag/config.py` must be empty.
