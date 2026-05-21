# C6 Surface and Provider Verify — Design

## Boundaries

C6 is the activation surface for C1-C5. It may touch config, request models,
eval/replay CLIs, and production provider verification. It should not change
the classic retrieval algorithm, reranker scoring, answer prompt generation, or
provider HTTP implementations.

## Contracts

### Config

Add `AgenticConfig` to `Settings`:

- `mode: Literal["classic", "agentic"] = "classic"`
- `decision: AgenticDecisionConfig = Field(default_factory=...)`

`AgenticDecisionConfig` mirrors the shape operators already know from
`AnswerConfig`, but remains disabled/noop by default. Empty `model_id`,
`base_url`, `chat_completions_url`, and `api_key_env` mean "fall back to
AnswerConfig" at resolution time. This avoids requiring duplicate provider
settings for deployments that use the same model family for answer and
decision calls.

### API Requests

Add fields to the base `SearchRequest` so Retrieve/Answer inherit them:

- `mode: Literal["classic", "agentic"] | None`
- `agentic: AgenticRequestOverrides | None`

The initial override block should be small and forward-compatible: optional
decision-enable and budget knobs only. This keeps request parsing stable while
leaving richer tool policy controls for follow-up work.

### Mode Resolution

Create a small pure helper for:

```text
request.mode > forced_mode > settings.agentic.mode
```

The helper returns both `mode` and `source` for plan stamping. It must be free
of FastAPI imports so eval, replay, and API can reuse it.

### Plan Stamping

When the mode source is not organic settings default, copy/update
`QueryPlan.strategy` with safe metadata:

- `mode`
- `mode_source`
- `forced_mode` when applicable
- `forced_mode_reason`

No raw query text or answer/provider payloads are stored.

### Eval and Replay

`run_eval(force_mode=...)` records the value in `config_snapshot`; the eval CLI
passes `--force-mode` through to the runner. The current eval runner still uses
classic search execution; C6 exposes and records the mode surface so later eval
gates can switch to the agentic execution path without another CLI contract
change.

Replay CLI similarly accepts `--force-mode` and reports it in the replay
report. Stored plan rows are read-only.

### Provider Verify

`production_provider_verify` performs a decision check when either:

- `settings.agentic.mode != "classic"`
- `settings.agentic.decision.enabled is True`

The check should be local and deterministic in unit tests. It validates config
resolution and env readiness, and can be extended later to make a strict JSON
tool-call provider request. Report JSON/Markdown includes the check like all
other provider checks.

## Compatibility

- Defaults keep `agentic.mode=classic`; existing callers that omit fields keep
  current behavior.
- Pydantic rejects invalid modes before execution.
- Env precedence follows the existing Settings rule:
  `env > .env > YAML init data > defaults`.

## Rollback

The change is isolated to config/request/report surfaces. If needed, remove the
new config fields, request fields, CLI flags, and provider verify check without
touching retrieval/reranker/answer internals.
