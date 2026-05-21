# Agentic CRAG-lite Grader

> Child C4 of `.trellis/tasks/05-21-agentic-rag-mode-toggle`.
> Depends on C1 loop foundation, C2 router, and C3 iterative loop.

## Goal

Implement flavor C: derive `GradeOutcome` from `RerankResult` using local,
deterministic thresholds. This gives the C3 iterative loop a real
`high/low/inconclusive/no_signal` signal without adding an LLM judge or
changing the reranker dispatcher.

## User Value

- Weak first-pass retrieval can trigger rewrite + second retrieval.
- Strong rerank evidence can stop early and finalize.
- Inconclusive reranker scores are explicitly visible in `plan_steps` instead
  of being silently treated as success.

## Requirements

- **R1 — Grader module.** Add `src/tagmemorag/agentic/grader.py` with
  `CragGradeThresholds` and `grade_rerank_result(...)`.
- **R2 — Reranker zero-touch.** Keep `src/tagmemorag/reranker/**` unchanged.
  C4 only reads `RerankResult.items[*].calibrated_score`,
  `vendor_used`, `cache_status`, and warnings.
- **R3 — Deterministic signals.**
  - `cache_status == "skipped"` or `vendor_used == "noop"` -> `no_signal`.
  - no items -> `low`.
  - top1 score >= high threshold and margin >= margin threshold -> `high`.
  - top1 score <= low threshold -> `low`.
  - otherwise -> `inconclusive`.
- **R4 — GradeTool integration.** `GradeTool` calls dispatcher exactly as
  before, then delegates to `grade_rerank_result` and returns the computed
  grade in payload.
- **R5 — Config-later discipline.** C4 may expose threshold dataclass defaults
  but must not add `AgenticConfig`; C6 wires settings/config later.
- **R6 — Optional LLM judge remains out.** Do not call an LLM. If a class or
  protocol is needed for future LLM-judge escalation, it must be a stub only.
- **R7 — Loop integration.** Existing C3 driver behavior must consume the
  computed `low` signal and iterate.
- **R8 — No public surface.** Do not edit `api.py`, `cli.py`, `config.py`, or
  provider verification.

## Acceptance Criteria

- [x] **AC4.1 — Signal derivation.** Unit tests cover high, low,
      inconclusive, no-signal, and empty-item cases.
- [x] **AC4.2 — Margin matters.** A high top1 score with insufficient margin
      returns `inconclusive`, not `high`.
- [x] **AC4.3 — GradeTool uses computed grade.** GradeTool payload reflects
      `grade_rerank_result`, not the old C1 fixed `no_signal`.
- [x] **AC4.4 — Low signal drives C3 loop.** A GradeTool/driver harness with
      low then no_signal executes rewrite and second retrieve.
- [x] **AC4.5 — No reranker source diff.** Diff for `src/tagmemorag/reranker`
      is empty.
- [x] **AC4.6 — No public surface diff.** Diff for API/CLI/config/provider
      verify is empty.
- [x] **AC4.7 — C1-C3 regressions stay green.** Agentic regression set and
      full `pytest -q` pass.

## Out of Scope

- LLM judge escalation and decision model provider verification.
- Public threshold config, request overrides, or eval force-mode.
- Quality threshold claims on `agentic_low_recall_recovery.jsonl`; that
  integrated eval waits for C6 surface wiring.
