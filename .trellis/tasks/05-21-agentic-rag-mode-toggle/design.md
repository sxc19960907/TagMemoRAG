# Agentic RAG Mode Toggle — Technical Design

> Companion to `prd.md`. PRD owns "what / why / accept"; this file owns
> "how it fits together". Decisions cited as Dn correspond to PRD's
> Resolved Decisions D1–D7.

## 1. Boundaries

Touched modules (additive only — no classic-path code paths change shape):

- `src/tagmemorag/config.py` — add `AgenticConfig`, `AgenticDecisionConfig`.
- `src/tagmemorag/api.py` — add `mode` + `agentic` fields to
  `SearchRequest` / `RetrieveRequest` / `AnswerRequest`; route to driver
  when `mode == agentic`.
- `src/tagmemorag/queryplan/plan.py` — extend `QueryPlan` (no field
  removal) with optional `steps_enabled: bool` runtime flag (does NOT
  serialize); `Budget` gains `max_iterations`, `max_agent_tokens`,
  `max_tool_calls`.
- `src/tagmemorag/queryplan/plan_log.py` — add `plan_steps` table and
  `append_step_async`; existing `plan_basic` / `update_result_async`
  untouched.
- **New package** `src/tagmemorag/agentic/` (no overlap with existing
  modules):
  - `driver.py` — loop driver.
  - `state.py` — `AgentState`, `GradeOutcome`, `StepRecord`.
  - `tools/` — `base.py`, `registry.py`, `retrieve.py`, `grade.py`,
    `rewrite.py`, `final.py`.
  - `router.py` — flavor A classifier.
  - `grader.py` — flavor C grader (reads `RerankResult`).
  - `decision.py` — `DecisionGenerator` (wraps answer LLM by default per
    D5).
  - `replay.py` — `StepReplayVerdict`, `AgentRunReplayVerdict` helpers.
- `src/tagmemorag/replay/runner.py` — branch on
  `plan.has_steps` → call `agentic.replay.replay_steps` and merge results.
- `src/tagmemorag/production_provider_verify.py` — add `decision` step,
  gated by D5.
- `src/tagmemorag/observability/metrics.py` — register agent counters /
  histograms (see §6).
- `tests/fixtures/eval/` — add four new slices (D4) +
  `baselines/agentic_*.json` (populated by child-1 baseline run).

Untouched (must remain byte-equivalent on classic path):

- `src/tagmemorag/reranker/*` (D6 zero-touch).
- `src/tagmemorag/retrieval.py`, `search_runtime.py`, `wave_*`.
- `src/tagmemorag/answer/openai_compatible.py` (D5 adapter wraps it from
  outside, no internal change).
- Existing `plan_basic` / `evidence_ids` / `rerank_json` columns.

## 2. Data Flow

### 2.1 Classic mode (unchanged)

```
request → build_plan → execute_search → rerank.dispatch → answer.generate
        → plan_log.insert_basic → plan_log.update_result_async (background)
```

### 2.2 Agentic mode

```
request
  → resolve_mode(request, settings, eval_force)        # D3
  → build_plan (extended Budget: max_iter/max_tokens/max_tool_calls)
  → if QueryPlan.persist == False: downgrade to classic (D3 hard guard)
  → driver.run_agent(plan, tools, guard, decision_gen):
      step 0: tools["retrieve"](query)          # flavor B initial
      loop until terminate:
        grader.grade(rerank_result) → GradeOutcome (D6 three signals)
        action = decide(state, grade):
          rule_fastpath if signal ∈ {high, low, no_signal}
          else decision_gen.choose_tool(state, registry.openai_schemas())
        plan_log.append_step_async(plan_id, step_idx, action, observation)
        observation = tools[action.name](action.args)
        state.update(action, observation)
        if budget.exhausted(state) or action.name == "final": break
      return state.finalize()  # graceful degrade on breach (R4)
  → plan_log.update_result_async (background, classic columns same shape)
```

## 3. Key Contracts

### 3.1 `AgenticConfig` (new in `config.py`)

```python
class AgenticConfig(BaseModel):
    mode: Literal["classic", "agentic"] = "classic"        # default-off
    enabled_flavors: list[Literal["adaptive","iterative","crag"]] = []
    max_iterations: int = Field(default=3, ge=1, le=8)
    max_agent_tokens: int = Field(default=4096, ge=128)
    max_tool_calls: int = Field(default=12, ge=1)
    grader_top1_threshold: float = 0.6      # τ for `high` signal
    grader_low_threshold: float = 0.2       # τ for `low` signal
    grader_inconclusive_margin: float = 0.05
    grader_depth_threshold: int = 3
    crag_llm_judge_enabled: bool = False     # default off per D1.C
    decision: AgenticDecisionConfig = Field(default_factory=AgenticDecisionConfig)
```

### 3.2 `AgenticDecisionConfig` (D5)

```python
class AgenticDecisionConfig(BaseModel):
    enabled: bool = False
    provider: Literal["noop", "openai_compatible"] = "noop"
    model_id: str = ""              # empty → fallback to AnswerConfig
    base_url: str = ""              # empty → fallback to AnswerConfig
    api_key_env: str = ""           # empty → fallback to AnswerConfig
    timeout_seconds: float = Field(default=15.0, gt=0.0)
    max_output_tokens: int = Field(default=256, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    tool_schema_mode: Literal["openai_tools","json_object"] = "openai_tools"
    json_strict: bool = True
```

### 3.3 Request overrides (D3)

```python
class AgenticOverrides(BaseModel):
    max_iterations: int | None = None
    enabled_flavors: list[Literal["adaptive","iterative","crag"]] | None = None
    crag_llm_judge_enabled: bool | None = None

class SearchRequest(BaseModel):   # additive
    ...
    mode: Literal["classic","agentic"] | None = None
    agentic: AgenticOverrides | None = None
```

Resolution order (D3): per-request override > eval `force_mode` >
settings default. Eval/replay CLI uses `--force-mode classic|agentic`
which stamps `plan.strategy["forced_mode"]` for provenance.

### 3.4 `plan_steps` table (new; extends `plan_log.py`)

```sql
CREATE TABLE IF NOT EXISTS plan_steps (
  plan_id          TEXT NOT NULL,
  step_idx         INTEGER NOT NULL,
  tool             TEXT NOT NULL,
  args_json        TEXT NOT NULL,
  observation_json TEXT NOT NULL,
  signal           TEXT NOT NULL,    -- "high"|"low"|"inconclusive"|"no_signal"
  decision_source  TEXT NOT NULL,    -- "rule"|"llm"
  top1_score       REAL,
  margin           REAL,
  depth            INTEGER,
  rationale        TEXT,
  tokens           INTEGER,
  latency_ms       INTEGER,
  ts               TEXT NOT NULL,
  PRIMARY KEY (plan_id, step_idx)
);
```

Write path mirrors existing `BackgroundWriter` pattern (non-blocking,
drops on overflow, metric on failure). Read path is `replay.load_steps`.

### 3.5 Tool registry + protocol (D2)

```python
class AgentTool(Protocol):
    name: str
    description: str
    input_schema: dict          # OpenAI tools JSON schema
    def __call__(self, args: dict, ctx: AgentStepCtx) -> ToolObservation: ...

TOOLS = AgentToolRegistry()
TOOLS.register(RetrieveTool(search_runtime))   # wraps execute_search
TOOLS.register(GradeTool(reranker_dispatcher)) # zero-touch reuse (D6)
TOOLS.register(RewriteTool(intent_module))     # reuses queryplan.intent
TOOLS.register(FinalTool(answer_generator))    # wraps existing generator
```

`registry.openai_schemas()` produces the JSON Schema list fed to the
decision LLM.

### 3.6 `GradeOutcome` (D6)

```python
@dataclass(frozen=True)
class GradeOutcome:
    top1_score: float
    margin: float
    depth: int
    signal: Literal["high","low","inconclusive","no_signal"]
    reason: str               # human-readable; written to plan_steps
```

`signal` derivation (deterministic, hard-coded):

| Condition | signal |
|---|---|
| `cache_status == "skipped"` or `vendor_used == "noop"` | `no_signal` |
| `top1 ≥ τ_high_top1` and `margin ≥ τ_margin` and `depth ≥ τ_depth` | `high` |
| `top1 ≤ τ_low_top1` and `depth < τ_depth` | `low` |
| otherwise | `inconclusive` |

### 3.7 Decision rules (D6)

| State | Action | Source |
|---|---|---|
| `step == 0` | `retrieve` | rule |
| `signal == high` and `step ≥ 1` | `final` | rule |
| `signal == low` and `step < max_iter` | `rewrite` | rule |
| `signal == low` and `step == max_iter` | `abort` → graceful degrade | rule |
| `signal == no_signal` | classic fallback (final using classic pipeline) | rule |
| `signal == inconclusive` | call decision LLM → tool call JSON | llm |

### 3.8 Replay verdict (D7)

```python
@dataclass
class StepReplayVerdict:
    step_idx: int
    tool_match: bool            # MUST
    signal_match: bool          # MUST
    args_schema_match: bool     # MUST (key-set only)
    decision_source_match: bool # MUST
    evidence_jaccard: float     # tolerance, default τ_low=0.80
    rationale_logged: bool      # informational

@dataclass
class AgentRunReplayVerdict:
    n_steps_match: bool         # MUST
    step_verdicts: list[StepReplayVerdict]
    final_top1_match: bool      # reuses top1_stability
    final_evidence_jaccard: float
    overall: Literal["match", "tolerated_drift", "diverged"]
```

LLM steps replay via stored `tool` + `args`; **never re-prompt the LLM**.

## 4. Compatibility & Migration

- **Classic path byte-equivalence**: all new fields on `SearchRequest`
  default to `None`; `AgenticConfig.mode` defaults to `classic`;
  `agentic/` is dead code until called. Classic eval fixtures must
  produce identical bytes vs `main` (AC1, AC5).
- **`plan_steps` table is opt-in**: created with `IF NOT EXISTS`; classic
  plans have zero rows in this table; no schema migration required for
  existing kbs.
- **Private KB hard guard** (D3): when `QueryPlan.persist == False`, the
  driver downgrades to classic and emits
  `agentic.private_kb_downgrade`. No new ACL machinery needed.
- **Rollback**: setting `agentic.mode = classic` returns the system to
  pre-feature behavior immediately; `plan_steps` rows for prior runs are
  left in place (read-only data).

## 5. Trade-offs

- **Self-built loop vs framework (D2)**: trades 800–1200 LOC of in-repo
  code for single-source-of-truth replay and zero dependency drift.
- **Reranker reuse vs grader service (D6)**: trades a minor coupling
  (driver depends on `RerankResult.calibrated_score`) for not
  re-implementing cache + circuit_breaker + calibration.
- **Trajectory replay vs full re-generation (D7)**: trades the ability to
  detect prompt-level regressions for replay survivability across vendor
  changes. Acceptable because the production gate is the AC2 eval slice,
  not replay.
- **No per-KB plane (D3)**: trades flexibility for not building a new
  per-KB config table; callers can express per-KB selection via the
  per-request override using their own mapping.

## 6. Operational Hooks

### 6.1 Observability (R6)

OTel spans (one per layer):

```
agentic.run                       (root span, plan_id attribute)
  agentic.step                    (per iteration, step_idx attribute)
    agentic.tool.<name>           (retrieve | grade | rewrite | final)
    agentic.decision              (rule | llm; signal attribute)
```

Counters & histograms (Prometheus, via `observability/metrics.py`):

- `agentic_runs_total{mode, flavor, outcome}` — outcome ∈
  `match|tolerated_drift|diverged|budget_exhausted|private_kb_downgrade`
- `agentic_steps_per_run` (histogram)
- `agentic_tool_calls_total{tool, source}` — source ∈ `rule|llm`
- `agentic_decision_latency_ms` (histogram, by source)
- `agentic_budget_exhausted_total{reason}` — reason ∈
  `max_iterations|max_agent_tokens|max_tool_calls|guard_timeout`
- `agentic_grader_signal_total{signal}`
- `agentic_replay_verdict_total{outcome}`

### 6.2 Provider verification (R7, D5)

`run_production_provider_verify` adds a `decision` step **only when**
`agentic.mode != classic` OR `agentic.decision.enabled == True`. The
smoke runs 1–2 frozen fixtures asserting strict tool-call JSON; failure
flips verify red. Report adds a `decision` section.

### 6.3 Graceful degrade (R4)

On any of: budget breach, tool exception (after circuit breaker),
decision LLM exception, `signal == no_signal` with no remaining classic
fallback path — the driver returns the last successful retrieval +
classic answer wrapped in `AnswerGeneration`, sets
`plan.strategy["agentic_degraded_reason"]`, and emits
`agentic.budget_exhausted` or `agentic.tool_error` events. Never raises
5xx.

## 7. Child Task Topology (per Trellis parent/child guidance)

Dependencies recorded here for planning; each child task duplicates its
own dependency declarations in its own `prd.md` / `implement.md`.

```
agent-loop-driver  (foundation)
  ├── agentic-adaptive-router      depends on driver
  ├── agentic-iterative-multihop   depends on driver
  │     └── agentic-crag-grader    depends on iterative + driver
  ├── agentic-budget-and-fallback  depends on driver
  └── agentic-surface-and-provider-verify  depends on driver +
                                          all flavors merged
```

Each child must independently:

1. Ship flag-off byte-equivalence on classic path.
2. Pass its slice of AC2 MUST gate (D4).
3. Carry its own `implement.jsonl` + `check.jsonl` for sub-agent runs.
