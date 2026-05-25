# Agentic Loop Driver and Plan Steps

> Child of `.trellis/tasks/05-21-agentic-rag-mode-toggle`. Foundation
> task: lands the loop driver + tool registry + `plan_steps` table +
> `Budget` extension. Other agentic children (router / iterative / crag /
> budget / surface) plug into the contracts this task locks in.

## Goal

Build the **agentic execution skeleton** that satisfies parent decisions
D1–D7 without yet implementing any agentic flavor logic. Concretely:

- A self-built loop `driver` (D2) that walks `plan → step → grade →
  decide → tool → observe → next-step` in bounded form.
- A typed `AgentTool` protocol + `AgentToolRegistry` whose tool I/O
  matches the OpenAI tool-calling schema (D2).
- An additive `plan_steps` SQLite table + `BackgroundWriter` write path
  inside `queryplan/plan_log.py` (D6, D7 evidence).
- An extension to `Budget` with `max_iterations`, `max_agent_tokens`,
  `max_tool_calls` (D1.R4 prerequisite).
- A `replay` extension that detects `plan.has_steps` and dispatches to
  `trajectory replay` per D7.
- Four **classic-equivalent stub tools**: `RetrieveTool`, `GradeTool`
  (always returns `no_signal`), `RewriteTool` (identity), `FinalTool` —
  so an agentic run with `enabled_flavors=[]` produces byte-identical
  output to a classic run on the same query (decision rule for
  `no_signal` per D6 ensures the path collapses to classic).

This task does **not** ship: flavor A classifier, flavor B rewrite
logic, flavor C grader signal computation, decision LLM call, eval/CLI
surface, provider verification — those are dedicated child tasks.

## Confirmed Facts (from parent + repo inspection)

- Parent's `design.md §1` already enumerates touched modules; this task
  owns the agentic foundation subset:
  - new package `src/tagmemorag/agentic/` (driver, state, tools/, replay)
  - `queryplan/plan.py` Budget extension
  - `queryplan/plan_log.py` `plan_steps` table + writer path
  - `replay/runner.py` `has_steps` branch
- The contracts `AgenticConfig`, `AgenticDecisionConfig`, request-side
  overrides, eval `--force-mode` flag, `production_provider_verify`
  decision step are **owned by C6**, not this task.
- D6 invariant: `RerankerDispatcher`'s cache key is `(plan, candidates)`
  and must remain step-idx-independent. C1 lands a regression test that
  fails if a future commit adds `step_idx` to the cache key.
- D7 trajectory replay: `decision_source == "llm"` steps replay from
  stored args without re-prompting; in C1 every step is `decision_source
  == "rule"` because no flavor is enabled, so the replay path is exercised
  only for rule-driven steps. LLM trajectory replay surface is built and
  unit-tested; integration tests come with C2/C3/C4.

## Requirements

- **R1 — Package layout.** Create `src/tagmemorag/agentic/` with
  `__init__.py`, `driver.py`, `state.py`, `decision.py`, `replay.py`,
  and `tools/{__init__.py, base.py, registry.py, retrieve.py, grade.py,
  rewrite.py, final.py}`. No imports from `agentic` outside this package
  in C1 (entry point wiring is C6).
- **R2 — Tool protocol & registry.** `AgentTool` is a `Protocol` with
  `name: str`, `description: str`, `input_schema: dict` (JSON Schema /
  OpenAI tool format), and `__call__(args, ctx) -> ToolObservation`.
  `AgentToolRegistry.register(tool)`, `.get(name)`, `.openai_schemas()`.
- **R3 — Driver loop.** `run_agent(plan, registry, guard,
  decision_gen, settings)` executes:
  1. step 0 → `retrieve`
  2. each subsequent step: read `RerankResult` from last `retrieve` /
     stub `grade`, derive `signal` (the helper lives here, even though
     real signal computation is C4's job; in C1 the helper always
     returns `no_signal` because GradeTool stub returns sentinel)
  3. `signal == no_signal` → classic-fallback path → `final`
  4. emit `StepRecord` for each step, `append_step_async` to plan_log
  5. exits on `final` action or budget exhaustion
- **R4 — Budget extension.** `Budget` (in `queryplan/plan.py`) gains
  optional `max_iterations: int = 3`, `max_agent_tokens: int = 4096`,
  `max_tool_calls: int = 12`. `to_dict` serializes only when non-default
  to keep `coffee.jsonl` byte-equivalent. `BudgetGuard` exposes
  `iterations_left`, `tokens_left`, `tool_calls_left`, all with
  `consume(...)` decrement helpers.
- **R5 — `plan_steps` schema.** Add table per parent design §3.4. Use
  `CREATE TABLE IF NOT EXISTS`; never alter existing tables. Writer path
  follows existing `BackgroundWriter` pattern: enqueue, drop on
  overflow, structured failure metric, never raise.
- **R6 — Replay branch.** `replay/runner.replay_plan` reads
  `plan_steps` for the `plan_id`; if rows exist (`plan.has_steps`),
  delegate to `agentic.replay.replay_steps` which produces an
  `AgentRunReplayVerdict` (D7). Classic path (no rows) unchanged.
- **R7 — Stub tools (classic-equivalent).**
  - `RetrieveTool.__call__`: wraps current `execute_search` /
    `build_retrieve_response` exactly; returns `RerankResult`-shaped
    observation.
  - `GradeTool.__call__`: returns a fixed
    `GradeOutcome(signal="no_signal", reason="c1_stub")`. Wraps a
    `dispatcher.rerank(...)` call so the D6 invariant test has a real
    caller; the call's output is recorded but the signal is forced to
    `no_signal` by the stub so the driver short-circuits to final.
  - `RewriteTool.__call__`: identity — returns the input query
    unchanged with `reason="c1_stub_identity"`.
  - `FinalTool.__call__`: wraps the existing `answer.generate(...)`
    pipeline byte-equivalent.
- **R8 — Decision generator scaffolding.** `DecisionGenerator` Protocol
  + `RuleOnlyDecisionGenerator` (always returns `None`, forcing the
  driver into rule fastpath). `OpenAICompatibleDecisionGenerator` is
  **declared but not implemented** in C1 (`raise NotImplementedError`)
  — the LLM decision path is verified by C2 onwards. `create_decision_generator`
  fallback to `AnswerConfig` (D5) is owned by C6.
- **R9 — Default-off discipline.** `agentic` package code is unreachable
  unless caller explicitly invokes `run_agent`. C1 does **not** wire
  `run_agent` into `api.py` / CLI / eval — that surface is C6.
- **R10 — D6 invariant test.** Add a unit test asserting:
  `dispatcher._cache_key(plan, candidates_A)` ≠
  `dispatcher._cache_key(plan, candidates_B)` when `candidates_A !=
  candidates_B`, and equal when `candidates` are identical regardless
  of any agent state. Test must reject any future PR that adds
  `step_idx` to the key.
- **R11 — Baseline pass.** Run an honest baseline pass and write
  `tests/fixtures/eval/baselines/agentic_simple_passthrough.json`,
  `tests/fixtures/eval/baselines/agentic_multihop.json`,
  `tests/fixtures/eval/baselines/agentic_low_recall_recovery.json`,
  `tests/fixtures/eval/baselines/agentic_budget_breach.json` using the
  classic pipeline (since no flavor is implemented yet, all four are
  classic baselines). Subsequent flavor children diff against these.
- **R12 — Fixture creation.** Create skeletal versions of the four new
  JSONL slices named in D4. C1 only seeds the **schema and a small
  number of cases** (3–5 per slice) so child tasks can iterate. Final
  curation belongs to whichever flavor child uses each slice.

## Acceptance Criteria

- [ ] **AC1.1 — Classic byte-equivalence (Hard MUST).** With
      `agentic.mode = classic` (default), `coffee.jsonl`,
      `realmanuals.jsonl`, `product_manuals.jsonl` all produce
      byte-identical answer + ranking output vs `main`. Diff = 0.
- [ ] **AC1.2 — Agentic-stub byte-equivalence (Hard MUST).** With
      `agentic.mode = agentic`, `enabled_flavors = []`, all four stub
      tools registered, `agentic_simple_passthrough.jsonl` produces
      output byte-identical to the same suite at `agentic.mode =
      classic`. This proves the agentic path collapses to classic when
      no flavor is enabled.
- [ ] **AC1.3 — `plan_steps` writes.** A stub agentic run writes ≥ 1
      row per case to `plan_steps` (one for the rule-driven
      `final`-via-`no_signal` step). Schema columns populated per
      parent design §3.4.
- [ ] **AC1.4 — Replay verdict.** Running the C1 stub agentic suite
      through `replay/runner.replay_plan` produces verdicts that are
      **all `match`** (not `tolerated_drift` and not `diverged`),
      because every step is `decision_source = "rule"` and tools are
      deterministic.
- [ ] **AC1.5 — D6 invariant test.** New unit test in
      `tests/unit/test_reranker_dispatcher_cache_key_invariant.py`
      passes; the test would fail if `step_idx` were added to the cache
      key.
- [ ] **AC1.6 — Baselines committed.** Four baseline JSON files live
      in `tests/fixtures/eval/baselines/agentic_*.json`, each with
      computed metrics + provenance (run timestamp, git sha, build_id).
- [ ] **AC1.7 — Tests + lint green.** `ruff check` clean,
      `mypy src/tagmemorag/agentic` clean, `pytest tests/unit -q -k
      agentic` green, full `pytest -q` green (regression for classic
      path).
- [ ] **AC1.8 — No reranker / answer source diff.** Diff against `main`
      for `src/tagmemorag/reranker/**` and
      `src/tagmemorag/answer/openai_compatible.py` is empty. (Enforced
      by review; D5 / D6 promised these would not be touched in C1.)

## Out of Scope (handled by other children)

- Flavor A classifier (C2 `agentic-adaptive-router`).
- Flavor B rewrite + multi-hop planner (C3 `agentic-iterative-multihop`).
- Flavor C grader signal computation + LLM-judge (C4
  `agentic-crag-grader`).
- BudgetGuard exhaustion → graceful degrade event surface (C5
  `agentic-budget-and-fallback`).
- `AgenticConfig` / `AgenticDecisionConfig` Pydantic models, request
  override fields, eval/replay `--force-mode`, provider verify decision
  step (C6 `agentic-surface-and-provider-verify`).
- Wiring `run_agent` into `api.py` / CLI (C6).

## Dependencies (per Trellis parent/child guidance)

- Depends on: parent task's design.md §3.4 (plan_steps schema),
  §3.5 (registry/protocol), §3.7 (decision rules), §3.8 (replay
  verdict).
- Blocks: C2 / C3 / C4 / C5 (all need driver + registry); C6 needs
  driver to exist before wiring surface.

## Notes

- Complex task: requires `prd.md` + `design.md` + `implement.md` before
  `task.py start` per Trellis discipline. **Note**: parent's earlier
  `task.py start` on this child auto-pushed status to `in_progress` as
  a side effect of switching active task; we are **not** beginning
  implementation until the user has reviewed all three planning
  artifacts in this child.
