# Agentic Budget and Fallback

> Child C5 of `.trellis/tasks/05-21-agentic-rag-mode-toggle`.
> Depends on C1-C4 agentic foundation, router, iterative loop, and grader.

## Goal

Make agentic budget exhaustion and private-KB downgrade explicit,
deterministic, and replayable. C5 does not add public config/API fields; it
uses the `Budget` fields already landed in C1 and the `QueryPlan.persist`
privacy flag already present on plans.

## User Value

- Agentic mode fails closed to the known classic answer instead of raising
  when budget runs out.
- Operators can inspect `plan_steps` and see the exact fallback reason.
- Private/sensitive KBs never enter multi-step agentic execution.

## Requirements

- **R1 — Unified fallback helper.** Agentic fallback should use one path that
  returns `classic_fallback`, sets `AgentRunResult.fallback_reason`, and
  optionally writes a `tool="fallback"` step.
- **R2 — Budget reasons.** Preserve exact reasons from `BudgetGuard`:
  `max_iterations`, `max_agent_tokens`, `max_tool_calls`.
- **R3 — Private-KB hard guard.** If `plan.persist is False`, return classic
  fallback immediately with reason `private_kb_classic` and do not call
  router or tools.
- **R4 — Replayable fallback step.** When `plan_log` is supplied and plan
  persistence is allowed, budget fallback writes a deterministic rule step
  with safe payload only: fallback reason and history length. It must not
  include raw query text, answer text, snippets, or provider payloads.
- **R5 — No public surface.** Do not edit API, CLI, config, or provider
  verification. C6 owns request/config wiring and external verify.
- **R6 — Existing successful paths unchanged.** No-signal, route
  single-shot, high, inconclusive, and successful low-then-retrieve flows
  remain green.
- **R7 — No reranker/answer source diff.** Do not change
  `src/tagmemorag/reranker/**` or `src/tagmemorag/answer/openai_compatible.py`.

## Acceptance Criteria

- [x] **AC5.1 — Initial budget exhaustion falls back.** A plan with zero
      iterations returns `classic_fallback` with reason `max_iterations`.
- [x] **AC5.2 — Mid-loop budget exhaustion is replayable.** A low-signal loop
      that exhausts budget writes a final `tool="fallback"` step with the
      budget reason.
- [x] **AC5.3 — Token budget exhaustion covered.** A tool that consumes all
      agent tokens triggers fallback with reason `max_agent_tokens`.
- [x] **AC5.4 — Tool-call exhaustion covered.** Exhaustion before a next tool
      returns fallback with reason `max_tool_calls` when fallback exists.
- [x] **AC5.5 — Private KB downgrade.** `QueryPlan.persist=False` returns
      fallback with reason `private_kb_classic` before router/tool calls.
- [x] **AC5.6 — Fallback step is safe.** Fallback step payload contains no raw
      query or answer text.
- [x] **AC5.7 — C1-C4 regressions stay green.** Agentic regression set and
      full `pytest -q` pass.
- [x] **AC5.8 — No public/provider diff.** API/CLI/config/provider verify,
      reranker, and OpenAI-compatible answer files remain untouched.

## Out of Scope

- Public `agentic.budget_exhausted` metrics/events/spans. C5 stores a
  replayable fallback step; external observability can be wired later.
- API response warning shape and user-facing fallback messages. C6 owns
  public response contracts.
- Changing budget default values.
