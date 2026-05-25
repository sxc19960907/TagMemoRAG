# Agentic Adaptive Router

> Child C2 of `.trellis/tasks/05-21-agentic-rag-mode-toggle`.
> Depends on C1 commit `2340ca4c51c59e4935db1a0fc1bf49e176553bea`.

## Goal

Implement flavor A: an adaptive router that classifies each request into
`no_retrieval`, `single_shot`, or `multi_hop`, then lets the agentic driver
short-circuit simple single-shot requests to the classic path. C2 is still
default-off and internal: C6 owns public config/API/CLI/eval `mode` wiring.

## User Value

- Simple requests stay cheap and byte-equivalent even when agentic mode is
  eventually enabled.
- Complex requests become explicitly detectable before C3/C4 add iterative
  retrieval and CRAG grading.
- The routing decision is persisted into `plan_steps`, so replay can explain
  why a request did or did not enter the agent loop.

## Confirmed Facts

- C1 landed an isolated `src/tagmemorag/agentic/` package, `run_agent`,
  `AgentToolRegistry`, `StepRecord`, and `plan_steps`.
- Parent D1 defines adaptive routing categories:
  `no_retrieval | single_shot | multi_hop`.
- Parent D4 requires `agentic_simple_passthrough.jsonl` to be
  byte-equivalent across classic and agentic modes.
- Parent D3/C6 own `AgenticConfig`, per-request override, and eval
  `--force-mode`. C2 must not wire public surfaces.

## Requirements

- **R1 — Router contract.** Add `src/tagmemorag/agentic/router.py` with:
  `RouteKind`, `RouteDecision`, `AdaptiveRouter` Protocol, and
  `RuleBasedAdaptiveRouter`.
- **R2 — Deterministic rule router.** The first implementation is local,
  deterministic, and dependency-free. It may use query text plus existing
  `QueryPlan.intent`, `filters`, `strategy`, and budget fields. It must not
  call an LLM or provider.
- **R3 — Conservative classification.**
  - `single_shot`: normal answerable product/manual questions.
  - `multi_hop`: explicit comparative, stepwise, follow-up, or
    multi-entity questions.
  - `no_retrieval`: empty/out-of-scope requests, greetings, and queries that
    the existing planner marked `out_of_scope`.
  Ambiguous cases default to `single_shot`, not `multi_hop`, to preserve the
  simple-query byte-equivalence gate.
- **R4 — Driver preflight.** Extend `run_agent` with an optional router. If
  route is `single_shot`, return the supplied `classic_fallback` immediately
  and write a route `StepRecord` when `plan_log` is available. If no
  fallback is supplied, raise a clear error instead of inventing an answer.
- **R5 — No public surface.** Do not edit `api.py`, `cli.py`, `config.py`, or
  eval CLI in C2. C6 wires settings and request fields.
- **R6 — Replay compatibility.** Route steps are ordinary `plan_steps` rows
  with `tool="route"` and `decision_source="rule"`. Existing replay verdicts
  must classify them as deterministic rule steps.
- **R7 — Eval fixtures.** Use C1's
  `tests/fixtures/eval/agentic_simple_passthrough.jsonl` as the C2 hard gate.
  C2 may add a small router-specific unit fixture inside tests, but it must
  not change C1 baseline JSONs unless a bug in the baseline is found.
- **R8 — Default-off discipline.** Existing classic execution remains
  unreachable by C2 changes unless tests explicitly call the router/driver.

## Acceptance Criteria

- [x] **AC2.1 — Router contract exists.** `RouteDecision.to_dict()` is
      stable, contains no raw evidence snippets, and includes route, reason,
      confidence, and safe features.
- [x] **AC2.2 — Simple passthrough routes single-shot.** Every case in
      `agentic_simple_passthrough.jsonl` is classified as `single_shot`.
- [x] **AC2.3 — Multi-hop examples route multi-hop.** Representative
      comparison/stepwise tests classify as `multi_hop`.
- [x] **AC2.4 — Out-of-scope examples route no-retrieval.** Empty,
      greeting, and `Intent.OUT_OF_SCOPE` plans classify as `no_retrieval`.
- [x] **AC2.5 — Driver short-circuit.** With router enabled and
      `classic_fallback` supplied, `single_shot` returns the exact fallback
      object and performs no retrieve/grade/final tool calls.
- [x] **AC2.6 — Route step persisted.** A single-shot short-circuit run
      writes exactly one `tool="route"` step and no retrieve/grade/final
      steps before returning fallback.
- [x] **AC2.7 — C1 regressions stay green.** C1 agentic tests and full
      `pytest -q` remain green.
- [x] **AC2.8 — No surface diff.** Diff for `src/tagmemorag/api.py`,
      `src/tagmemorag/cli.py`, and `src/tagmemorag/config.py` is empty.

## Out of Scope

- Public `agentic.mode`, `enabled_flavors`, request overrides, eval
  `--force-mode`, and provider verification: C6.
- Iterative multi-hop execution after route=`multi_hop`: C3.
- CRAG score-derived signal computation: C4.
- Graceful budget-degrade event surface: C5.
- LLM/router-provider calls. C2 leaves an interface seam only; the first
  router is rule-based.

## Notes

- C2 is intentionally small. Its job is to make "agentic can decline to be
  fancy" a tested behavior before C3/C4 add real multi-step work.
