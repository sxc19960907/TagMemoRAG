# Agentic Surface and Provider Verify

> Child C6 of `.trellis/tasks/05-21-agentic-rag-mode-toggle`.
> Depends on C1-C5.

## Goal

Wire the public/default-off surface for agentic mode without changing classic
behavior by default. C6 owns configuration, per-request overrides, eval/replay
forced mode stamping, and production provider verification for the decision
model.

## Requirements

- **R1 — Default-off config.** Add `Settings.agentic` with
  `mode = classic | agentic`, default `classic`.
- **R2 — Decision config.** Add `Settings.agentic.decision` or equivalent
  nested `AgenticDecisionConfig` with defaults from parent D5:
  `enabled=False`, `provider=noop`, OpenAI-compatible fields, strict JSON/tool
  schema settings, and explicit fallback to `AnswerConfig` for empty provider
  fields.
- **R3 — Request overrides.** `SearchRequest`, `RetrieveRequest`, and
  `AnswerRequest` accept `mode: classic | agentic | None` plus an optional
  `agentic` override block. Omitted fields must preserve existing classic
  payload behavior.
- **R4 — Mode resolution.** Resolution order is per-request override, then
  forced eval/replay mode, then settings default. Private KB plans remain
  forced classic through the `QueryPlan.persist=False` guard shipped in C5.
- **R5 — Plan stamping.** When a non-organic mode is forced, stamp
  `plan.strategy["forced_mode"]` and a reason so replay/eval data does not
  contaminate organic A/B analysis.
- **R6 — Eval CLI/runner force mode.** `run_eval` and the eval CLI accept
  `force_mode=classic|agentic`; the report config snapshot records it.
- **R7 — Replay CLI force mode.** Replay CLI accepts
  `--force-mode classic|agentic`; replay output records the selected forced
  mode without changing stored plan rows.
- **R8 — Provider verify decision step.** `production_provider_verify` adds a
  `decision` check only when `agentic.mode != classic` or
  `agentic.decision.enabled=True`. The check must be deterministic and safe in
  tests, require any needed env var, and show in JSON/Markdown reports.
- **R9 — No secret leakage.** Config/report/provider verification details must
  never include raw API keys, raw prompts, snippets, vectors, or provider
  response bodies.
- **R10 — Classic byte-equivalence discipline.** With defaults, existing
  search/retrieve/answer/eval/replay/provider tests remain green.

## Acceptance Criteria

- [x] **AC6.1 — Config defaults.** `Settings().agentic.mode == "classic"`,
      decision config is disabled/noop, and env/YAML overrides work.
- [x] **AC6.2 — Request models.** Search/Retrieve/Answer requests parse
      `mode` and `agentic` overrides while omitted fields keep old payloads
      valid.
- [x] **AC6.3 — Mode resolution.** Per-request mode beats forced mode, forced
      mode beats settings, and invalid modes are rejected by Pydantic/CLI.
- [x] **AC6.4 — Plan stamping.** Forced eval/replay/request paths stamp
      sanitized mode metadata in `plan.strategy`.
- [x] **AC6.5 — Eval force mode.** Eval runner and CLI expose force-mode and
      report it in config snapshots.
- [x] **AC6.6 — Replay force mode.** Replay CLI accepts `--force-mode` and
      report output includes forced mode.
- [x] **AC6.7 — Provider verify decision.** Verify report includes a decision
      check only when agentic/decision config requires it, and env checks
      include the decision provider key when needed.
- [x] **AC6.8 — Default classic regression.** Targeted agentic surface tests
      and full `uv run pytest -q` pass.

## Out of Scope

- Replacing the C1-C5 stub tool registry with production retrieval/final tools.
- Live network calls to DeepSeek/SiliconFlow in unit tests.
- Per-KB agentic config plane.
- New observability metrics/spans beyond provider verify and plan stamping.
