# C1 Agent Loop Driver — Execution Plan

> Companion to C1 `prd.md` and `design.md`. PRD owns "what/why/accept";
> design owns "how it fits"; this file owns "what to do, in what order,
> and how to validate at each gate".
>
> **Important**: Parent's earlier `task.py start` on this child
> auto-flipped status to `in_progress`. We are **not** beginning
> implementation until the user has signed off on this child's three
> planning artifacts. This file is part of the review packet.

## 0. Operating Rules

- **No code changes are made until the user explicitly approves this
  child's planning artifacts.** Until then, every step below is
  documented intent, not action.
- **D6 enforcement is review-time, not just test-time**: any diff
  touching `src/tagmemorag/reranker/**` or
  `src/tagmemorag/answer/openai_compatible.py` is a hard reject in
  this child, even if tests pass.
- **AC1.1 / AC1.2 are blocking gates**: classic byte-equivalence and
  agentic-stub byte-equivalence must hold at every commit; failing
  either means rolling back the commit, not patching forward.
- **Implementation is dispatched to `trellis-implement` from the main
  session**, never inline in this conversation.

## 1. Pre-Flight Review (before implementation begins)

Gate items the user must confirm:

- [ ] `prd.md` reviewed — R1–R12, AC1.1–AC1.8, Out-of-Scope correct.
- [ ] `design.md` reviewed — §1 layout, §2 contracts, §3 compatibility.
- [ ] `implement.md` (this file) reviewed — ordering, gates, rollback.
- [ ] Branch decision: stay on parent's `agentic-rag-mode-toggle`
      branch, or create a child branch `agent-loop-driver`?
      **Recommended**: child branch off parent integration branch, so
      C1 can be PR-reviewed before C2–C6 layer on top.
- [ ] Curate `implement.jsonl` / `check.jsonl` with spec/research
      references that sub-agents need (see §7).

## 2. Implementation Order

Each step is one logical commit. Steps cannot be reordered without
re-reviewing this file.

### Step 2.1 — `Budget` extension (lowest-risk first)

- Edit `src/tagmemorag/queryplan/plan.py`:
  - Add `max_iterations`, `max_agent_tokens`, `max_tool_calls` to
    `Budget` with default values matching parent design §3.1.
  - Modify `Budget.to_dict` to emit agentic keys **only when
    non-default** (protects AC1.1).
- Add `BudgetGuard` accessors + `consume_*` helpers per design §2.4.
- **Validation**: `pytest tests/unit/test_queryplan_budget.py -q` green;
  add unit tests for `iterations_left / consume_iteration` etc.;
  re-run classic eval to confirm `budget_json` byte-equivalent on
  `coffee.jsonl`.

### Step 2.2 — `plan_steps` table + writer path

- Edit `src/tagmemorag/queryplan/plan_log.py`:
  - Add `_CREATE_STEPS_SQL` to `_ensure_schema`.
  - Add `_INSERT_STEP_SQL` parametric statement.
  - Add `PlanLog.append_step_async`, `load_steps`, `has_steps` per
    design §2.5.
  - Extend `BackgroundWriter.enqueue` shape to accept step rows
    (additive variant or new method, see §6 risk note).
- **Validation**:
  - `tests/unit/test_plan_log_steps.py::test_create_idempotent` (table
    `IF NOT EXISTS` semantics).
  - `tests/unit/test_plan_log_steps.py::test_append_and_load` (write
    then read three rows in order).
  - `tests/unit/test_plan_log_steps.py::test_no_steps_for_classic_plan`
    (`has_steps` False on plan with no steps).
  - Existing `tests/unit/test_plan_log.py` must remain green.

### Step 2.3 — `agentic/` package skeleton

- Create `src/tagmemorag/agentic/__init__.py` (empty exports for now).
- Create `tools/base.py`: `AgentTool` Protocol, `ToolObservation`,
  `AgentStepCtx` dataclasses.
- Create `tools/registry.py`: `AgentToolRegistry` with `register`,
  `get`, `has`, `names`, `openai_schemas`.
- Create `state.py`: `GradeOutcome`, `StepRecord`, `AgentState`.
- Create `decision.py`: `DecisionGenerator` Protocol +
  `RuleOnlyDecisionGenerator` + stub `OpenAICompatibleDecisionGenerator`
  that raises `NotImplementedError` (referenced in C2 onward).
- **Validation**: `mypy src/tagmemorag/agentic` clean;
  `tests/unit/test_agentic_tools_registry.py` covers
  `register/get/has/openai_schemas`.

### Step 2.4 — Four stub tools

- `tools/retrieve.py` — wraps `execute_search` +
  `build_retrieve_response`; returns `ToolObservation` whose
  `payload` mirrors the classic retrieve response shape.
- `tools/grade.py` — calls
  `dispatcher.rerank(plan, candidates, guard, query_text=...)` (so D6
  invariant test has a real caller), then returns
  `ToolObservation(payload={"signal": "no_signal", "reason":
  "c1_stub"}, rerank_result=...)`.
- `tools/rewrite.py` — identity; returns observation echoing the input
  query.
- `tools/final.py` — wraps `answer.generate(...)` byte-equivalent;
  returns observation containing the `AnswerGeneration` dict.
- **Validation**:
  `tests/unit/test_agentic_tools_stub.py` for each tool's `__call__`;
  `tests/unit/test_agentic_tools_grade_calls_dispatcher.py` asserts a
  dispatcher call happens even though `signal=no_signal`.

### Step 2.5 — Driver loop

- `driver.py` implements `run_agent` per design §2.6.
- Internal helpers: `_decide_next`, `_force_final`,
  `_terminate_with_classic_fallback`, `_build_step_record`,
  `_extract_grade`.
- The rule fastpath table is hard-coded in `_decide_next`:
  step 0 → `retrieve`; signal `no_signal` → `final`; everything else
  raises a guarded `NotImplementedError` with comment "owned by C2/C3/C4".
- **Validation**:
  `tests/unit/test_agentic_driver_loop.py`:
  - `test_runs_retrieve_then_final_on_no_signal_stub`
  - `test_writes_one_step_record_per_iteration`
  - `test_budget_iteration_exhaustion_triggers_classic_fallback`
  - `test_decision_gen_never_consulted_when_signal_is_no_signal`

### Step 2.6 — Replay branch

- `agentic/replay.py`: `StepReplayVerdict`, `AgentRunReplayVerdict`,
  `replay_steps(...)`.
- Edit `src/tagmemorag/replay/runner.py`:
  - In `replay_plan`, before the existing classic path, check
    `plan_log.has_steps(plan_id)`; if True, delegate to
    `agentic.replay.replay_steps`.
- **Validation**:
  - `tests/unit/test_agentic_replay_verdict.py` covers
    `tool_match / signal_match / args_schema_match /
    decision_source_match` MUST fields.
  - `tests/integration/test_agentic_stub_replay_match.py` runs a stub
    agentic plan, replays it, asserts `overall == "match"` (AC1.4).
  - Existing `tests/unit/test_replay_runner.py` must remain green —
    classic replay path unchanged.

### Step 2.7 — D6 invariant test

- `tests/unit/test_reranker_dispatcher_cache_key_invariant.py` per
  design §2.8.
- Comment explicitly references parent D6 + this child's R10 so future
  contributors can find context.
- **Validation**: test passes against current `main`; would fail under
  a synthetic mutation where `_cache_key` accepts `step_idx`.

### Step 2.8 — Four fixture skeletons

- Create:
  - `tests/fixtures/eval/agentic_simple_passthrough.jsonl`
  - `tests/fixtures/eval/agentic_multihop.jsonl`
  - `tests/fixtures/eval/agentic_low_recall_recovery.jsonl`
  - `tests/fixtures/eval/agentic_budget_breach.jsonl`
- Each starts with 3–5 cases following `load_eval_suite` schema (unique
  ids, well-formed JSONL); final curation is the consuming flavor
  child's job.
- **Validation**: `python3 -m tagmemorag.eval.dataset` smoke run on
  each file (or `pytest tests/unit/test_eval_dataset.py -k "load"`).

### Step 2.9 — Baseline pass (AC1.6)

- Run an honest baseline pass using the classic pipeline on the four
  agentic slices (since no flavor is implemented yet, all four are
  classic baselines).
- Output goes to `tests/fixtures/eval/baselines/agentic_*.json`, each
  including:
  - Computed `RankingMetrics` per case + aggregate.
  - Provenance: run timestamp (UTC), git sha, `build_id`, `kb_name`,
    classic-mode confirmation, used model ids (per Appendix-A
    discipline: vendor specifics stay under "as of" date).
- Commit the four files together with a single message referencing
  parent D4 deferred-threshold rationale.
- **Validation**: re-run the baseline command; output JSON must be
  byte-identical (deterministic baselines is itself a guarantee).

### Step 2.10 — Wire-up sanity (no public surface change)

- C1 does **not** wire `run_agent` into `api.py` / CLI / eval — that
  is C6's job.
- Add an internal `tests/integration/test_agentic_stub_byte_equivalence.py`
  that:
  - Constructs a minimal in-process harness invoking `run_agent` with
    the default registry from §2.3 / §2.4.
  - Asserts the resulting `AnswerGeneration` payload bytes match the
    classic `answer.generate(...)` payload for the same fixture set
    (AC1.2).
- **Validation**: integration test green on
  `agentic_simple_passthrough.jsonl`.

## 3. Validation Commands (composed)

```bash
# Static checks (every commit)
ruff check src tests
mypy src/tagmemorag/agentic src/tagmemorag/queryplan src/tagmemorag/replay

# Unit tier
pytest tests/unit -q -k "agentic or plan_log or queryplan_budget or replay_runner or reranker_dispatcher"

# Integration tier
pytest tests/integration -q -k "agentic_stub"

# Classic regression (AC1.1)
python3 -m tagmemorag.eval.runner \
  --suite tests/fixtures/eval/coffee.jsonl \
  --suite tests/fixtures/eval/realmanuals.jsonl \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --diff-against main

# Baseline pass (AC1.6)
for slice in agentic_simple_passthrough agentic_multihop \
             agentic_low_recall_recovery agentic_budget_breach; do
  python3 -m tagmemorag.eval.runner \
    --suite tests/fixtures/eval/${slice}.jsonl \
    --baseline-output tests/fixtures/eval/baselines/${slice}.json
done

# Full repo regression (AC1.7)
pytest -q

# D5 / D6 untouched assertion (AC1.8)
git diff main -- src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py
# expected: empty
```

## 4. Risky Files & Rollback Points

| File | Risk | Rollback |
|---|---|---|
| `src/tagmemorag/queryplan/plan.py` | `Budget.to_dict` shape regression breaks classic fixtures | Revert; conditional serialization is the only safeguard, retest before next push |
| `src/tagmemorag/queryplan/plan_log.py` | Background writer enqueue shape change could break existing update path | Keep step writes in a **separate** method or sentinel — never reuse the existing enqueue signature without a regression test |
| `src/tagmemorag/replay/runner.py` | `has_steps` branch must short-circuit cleanly; misordered branch breaks classic replay | Keep classic branch as **else** of an `if has_steps`; never insert new code before the classic branch |
| `src/tagmemorag/agentic/*` | New code; isolated | Delete package; no other module imports it in C1 |
| `tests/fixtures/eval/agentic_*.jsonl` | Bad JSONL kills the loader | `load_eval_suite` validates per-line; CI catches on first invalid case |
| `tests/fixtures/eval/baselines/agentic_*.json` | Baselines drift if model ids change between runs | Provenance stamped; re-run after any vendor change is normal |

Rollback rule of thumb: **C1 is six independent commits; any one can be
reverted without touching the others except 2.5 (driver) which depends
on 2.3 (registry) + 2.4 (stubs).**

## 5. Exit Criteria for C1

C1 moves to `completed` (`task.py finish`) only when:

- [ ] AC1.1–AC1.8 all green.
- [ ] Branch is in a state where it can be reviewed and merged into
      parent's integration branch without further fixup commits.
- [ ] Spec update (Phase 3.3) committed: a short note in
      `.trellis/spec/backend/architecture.md` introducing the
      `agentic/` package boundary (one paragraph + diagram bullet);
      ADR for D2 (self-built loop) referenced (parent task may already
      own the ADR — link, don't duplicate).
- [ ] No file in `src/tagmemorag/reranker/**` or
      `src/tagmemorag/answer/openai_compatible.py` changed.
- [ ] Baselines committed and reproducible.

## 6. Cross-Child Contract Stability

C1's outward-facing API (what C2–C6 depend on):

- `agentic.AgentTool` Protocol — must not change shape after C1 lands.
- `agentic.AgentToolRegistry` — `register / get / has / names /
  openai_schemas` only.
- `agentic.state.GradeOutcome` / `StepRecord` / `AgentState` —
  additive only after C1.
- `agentic.driver.run_agent` signature — fixed after C1.
- `Budget.max_iterations / max_agent_tokens / max_tool_calls` —
  fixed defaults.
- `plan_steps` table schema — fixed; later children may only **add**
  columns through a new migration step, never rename or drop.

Any future child needing to change any of these must open a parent-
level decision update and amend the parent `design.md`, not patch
silently.

## 7. JSONL Manifests (`implement.jsonl` / `check.jsonl`)

Curate before dispatching sub-agents:

- `implement.jsonl` rows: parent decision references (D1.D2.D3.D6.D7),
  parent design §3 contracts, the four touched files, the four stub
  tool files, the four fixture files.
- `check.jsonl` rows: classic regression suites
  (`coffee/realmanuals/product_manuals`), the new agentic stub
  byte-equivalence integration test, the D6 invariant unit test, the
  baseline reproduction command.

These manifests gate what sub-agents read on each turn; keep them
**short and targeted** — sub-agents will pull additional context
through the codebase-memory MCP as needed.

## 8. Sign-Off Checklist (this file is the contract)

- [x] User has read/approved C1 `prd.md` scope through session review.
- [x] User has read/approved C1 `design.md` scope through session review.
- [x] User has read/approved this `implement.md` scope through session review.
- [x] User explicitly said "可以，开始吧" before implementation
      lands on the C1 branch.

## 9. Implementation Result (2026-05-21)

- [x] Added isolated default-off `src/tagmemorag/agentic/` foundation:
      driver, state, decision scaffolding, replay verdicts, tool protocol,
      registry, and stub retrieve/grade/rewrite/final tools.
- [x] Extended `Budget` and `BudgetGuard` with agentic iteration, token,
      and tool-call limits; default serialization remains classic-compatible.
- [x] Added additive `plan_steps` SQLite table, async step writer, and
      load/has helpers for replay.
- [x] Added replay branch for plans with stored steps while preserving the
      classic path for plans without steps.
- [x] Added C1 eval slices and classic baseline JSONs with metrics,
      timestamps, build ids, model/search provenance, and per-case ranks.
- [x] Added eval report `config_snapshot.build_ids` so future baselines can
      keep build provenance without scraping storage internals.
- [x] Updated `.trellis/spec/backend/architecture.md` with the shipped
      agentic foundation boundary.

Deferred to later children by original scope:

- C6 still owns public `agentic.mode`, API/CLI/eval force-mode wiring, and
  formal classic-vs-agentic byte-equivalence through the real surface.
- C2/C3/C4 still own non-`no_signal` decisions, adaptive routing,
  iterative rewrite/multihop, and CRAG grading.
- C5 still owns richer graceful-degrade events beyond C1's hard budget guard.

Validation performed:

- `uv run pytest tests/unit/test_agentic_driver_loop.py tests/unit/test_eval_runner.py tests/unit/test_agentic_replay_verdict.py tests/unit/test_agentic_tools_registry.py tests/unit/test_agentic_tools_stub.py tests/unit/test_queryplan_plan.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_runner.py tests/unit/test_reranker_dispatcher_cache_key_invariant.py tests/unit/test_eval_dataset.py -q` → 59 passed.
- `uv run pytest -q` → 984 passed, 2 skipped.
- `git diff --check` → passed.
- `uv run ruff ...` and `uv run mypy ...` were attempted earlier in this
  C1 session but this repo environment does not install `ruff` or `mypy`;
  `py_compile` was used as the available static syntax gate.
- Diff against `master` for `src/tagmemorag/reranker/**` and
  `src/tagmemorag/answer/openai_compatible.py` is empty.
