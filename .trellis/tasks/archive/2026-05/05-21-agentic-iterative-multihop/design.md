# C3 Iterative Multi-hop — Technical Design

## 1. Module Boundary

Touched files:

- `src/tagmemorag/agentic/driver.py`
- `src/tagmemorag/agentic/tools/rewrite.py`
- `tests/unit/test_agentic_driver_loop.py`
- `tests/unit/test_agentic_tools_stub.py` or new focused tests
- `tests/unit/test_agentic_replay_verdict.py`

Forbidden in C3:

- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/reranker/**`
- `src/tagmemorag/answer/openai_compatible.py`

## 2. Driver Loop

Current C1/C2 flow is:

```text
optional route -> retrieve -> grade -> final
```

C3 changes the middle to a small rule loop:

```text
optional route
current_query = initial_query
retrieve(current_query)
while True:
  grade()
  if grade.signal in {"no_signal", "high", "inconclusive"}:
      final()
      break
  if grade.signal == "low":
      rewrite(current_query, grade.reason)
      current_query = rewrite.payload["query"]
      retrieve(current_query)
      continue
```

Notes:

- `high` and `inconclusive` finalization are temporary C3 behavior. C4/C6 may
  refine inconclusive into decision-LLM handling later.
- Each tool call still goes through `_call_tool`, so budget checks and
  `plan_steps` writes remain centralized.
- The final step receives the latest grade.

## 3. Rewrite Tool

`RewriteTool` remains deterministic and local.

Input schema:

```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string"},
    "reason": {"type": "string"},
    "append_terms": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["query"]
}
```

Behavior:

- Normalize whitespace.
- Append unique safe terms from `append_terms`, if provided.
- If no terms are provided, return the query unchanged with
  `reason="c3_no_terms_identity"`.
- Payload:
  - `query`
  - `original_query_hash` using SHA-256, not raw original query
  - `changed: bool`
  - `reason`

C3 does not invent domain-specific terms automatically. Tests can pass
`append_terms` through a custom rewrite tool or configured args in the driver
test harness to prove data flow.

## 4. Iteration Budget

Before every tool call, `_call_tool` already checks `guard.agent_exhausted()`.
C3 adds graceful fallback around loop continuation:

- If rewrite or second retrieve cannot run because budget is exhausted and
  `classic_fallback` exists, return it with reason `max_iterations`,
  `max_tool_calls`, or `max_agent_tokens`.
- If no fallback exists, keep the existing clear `RuntimeError`.

## 5. Step Ordering

Without router:

```text
0 retrieve
1 grade
2 rewrite
3 retrieve
4 grade
5 final
```

With C2 router returning `multi_hop`:

```text
0 route
1 retrieve
2 grade
3 rewrite
4 retrieve
5 grade
6 final
```

## 6. Replay

No new replay schema is required. `rewrite` is just another deterministic rule
tool step. Add a test that a stored sequence containing `rewrite` returns
`overall="match"`.

## 7. Compatibility

- No public surface changes.
- No changes to reranker or answer provider implementation.
- `router=None` and `grade.signal=="no_signal"` preserve current C1/C2 flow.
- C3 does not claim eval quality improvement on `agentic_multihop.jsonl`
  until C4/C6 provide real grader/surface wiring.
