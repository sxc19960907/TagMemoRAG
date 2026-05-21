# Agentic Iterative Multi-hop

> Child C3 of `.trellis/tasks/05-21-agentic-rag-mode-toggle`.
> Depends on C1 loop foundation and C2 adaptive router.

## Goal

Implement flavor B: when the agentic driver receives a deterministic
`GradeOutcome(signal="low")`, it performs a bounded `rewrite -> retrieve ->
grade` loop before finalizing. C3 provides the iteration mechanics and safe
rewrite contract; C4 owns deriving real low/high/inconclusive grader signals
from reranker scores.

## User Value

- Multi-hop requests can perform a second retrieval with a revised query
  instead of failing after one weak retrieval.
- The iterative trajectory is visible in `plan_steps`, so replay and eval can
  explain what changed between retrieval rounds.
- The feature remains internal/default-off until C6 wires public mode/config.

## Confirmed Facts

- C1 shipped `run_agent`, `RewriteTool` identity stub, `BudgetGuard`
  agentic counters, and `plan_steps`.
- C2 shipped `RuleBasedAdaptiveRouter`; `multi_hop` route continues into the
  C1 loop with an initial route step.
- Parent D1.B defines bounded iterative multi-hop as
  `retrieve -> grade -> rewrite -> retrieve`.
- Parent D4 expects `agentic_multihop.jsonl` to improve over C1 baselines in
  later integrated runs; C3 seeds the mechanics but may use deterministic
  tests rather than claiming quality improvement before C4/C6.

## Requirements

- **R1 — Driver low-signal loop.** Extend `run_agent` so `grade.signal ==
  "low"` triggers `rewrite`, then another `retrieve`, then another `grade`,
  until a terminal signal or agentic budget exhaustion.
- **R2 — Preserve existing fast paths.** `signal == "no_signal"` still
  finalizes exactly as C1; C2 `single_shot` route still short-circuits.
- **R3 — Rewrite tool contract.** Upgrade `RewriteTool` from identity stub to
  a deterministic local tool that accepts `query`, optional `reason`, and
  optional `append_terms`; returns a rewritten query plus safe metadata. It
  must not call an LLM or external provider.
- **R4 — PII masking compatibility.** Rewritten query text must be available
  to downstream retrieval, but persisted step payload should be compatible
  with existing `queryplan.privacy.mask_rewrites` rules where settings are
  available.
- **R5 — Bounded loop.** Respect `BudgetGuard.agent_exhausted()` before every
  tool call. On exhaustion, return supplied `classic_fallback` with a clear
  fallback reason; do not 5xx when fallback exists.
- **R6 — Step trajectory.** A low-signal iteration records ordered
  `retrieve`, `grade`, `rewrite`, `retrieve`, `grade`, `final` steps (plus
  optional C2 `route` step when router is used).
- **R7 — No public surface.** Do not edit `api.py`, `cli.py`, `config.py`, or
  eval CLI. C6 owns all public toggles.
- **R8 — No reranker/answer source diff.** Do not change
  `src/tagmemorag/reranker/**` or `src/tagmemorag/answer/openai_compatible.py`.

## Acceptance Criteria

- [x] **AC3.1 — Low signal iterates.** A unit harness with grade sequence
      `low -> no_signal` executes `retrieve, grade, rewrite, retrieve,
      grade, final` in order.
- [x] **AC3.2 — Rewrite output feeds second retrieve.** The second retrieve
      receives the query emitted by `RewriteTool`.
- [x] **AC3.3 — Budget exhaustion degrades.** If the loop budget is exhausted
      before the second retrieve and `classic_fallback` exists, the driver
      returns that fallback and records the fallback reason.
- [x] **AC3.4 — Existing no-signal path unchanged.** C1 no-signal driver
      tests still pass.
- [x] **AC3.5 — Route + multihop compose.** With C2 router returning
      `multi_hop`, the route step is followed by iterative steps with
      monotonic `step_idx`.
- [x] **AC3.6 — Replay sees iterative steps as match.** Stored rewrite and
      second-retrieve steps replay as deterministic rule steps.
- [x] **AC3.7 — C1/C2 regressions stay green.** C1/C2 agentic tests and full
      `pytest -q` pass.
- [x] **AC3.8 — No surface or provider diff.** Diff for API/CLI/config,
      reranker, and OpenAI-compatible answer files is empty.

## Out of Scope

- Real CRAG/reranker-derived low/high/inconclusive signal computation: C4.
- LLM rewrite generation or decision LLM tool calls.
- Public mode/config/API/eval provider wiring: C6.
- Agentic budget event/metric surface beyond returning fallback: C5.
- Changing C1 baseline JSON thresholds.

## Notes

- C3 is a mechanics task. The quality lift comes after C4 supplies meaningful
  low/high signals and C6 wires eval force-mode.
