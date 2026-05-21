# Agentic RAG Mode Toggle

## Goal

Add a flag-driven toggle so the same RAG entry points (`/search`, `/retrieve`,
`/answer`, CLI) can run in two modes:

- `classic` (default): current single-pass pipeline, **byte-equivalent** to
  today's behavior. This satisfies the project-wide default-off discipline.
- `agentic`: a multi-step decision loop that decides whether/what/how to
  retrieve, can iterate, can grade and self-correct, and can call tools, all
  bounded by `BudgetSpec`.

This is a **parent task**. Child tasks will be split during brainstorm so each
deliverable is independently verifiable (per Trellis parent/child guidance).

## User Value

- Operators keep the existing predictable, low-latency RAG for simple FAQ-style
  queries (cheap, observable, byte-equivalent).
- For complex / multi-hop / ambiguous questions, agentic mode raises end-to-end
  answer quality at higher cost — under explicit budget caps.
- Eval-as-driver: classic vs agentic must be A/B comparable inside the same
  `plan_store`, so we can prove when agentic actually wins.

## Confirmed Facts (from repo inspection)

- Existing pipeline is a single-pass linear flow. Key surfaces:
  - API: `src/tagmemorag/api.py` (≈2.4k lines, ~45 routes including
    `/search` `/retrieve` `/answer`).
  - QueryPlan: `src/tagmemorag/queryplan/` with classes `Intent`, `Budget`,
    `QueryPlan`, `PlanLog`, `BackgroundWriter`, `BudgetGuard`.
  - Retrieval: `src/tagmemorag/retrieval.py` + `search_runtime.py` +
    `wave_searcher.py` + `metadata_narrowing.py`.
  - Rerank: `src/tagmemorag/reranker/dispatcher.py` (cache + circuit_breaker
    + calibration + local_fallback).
  - Generation: `src/tagmemorag/answer/` with `AnswerGenerator` interface,
    `OpenAICompatibleAnswerGenerator.generate`, `build_answer_prompt`,
    `validate_generation_citations`, `create_answer_generator`.
  - Replay: `src/tagmemorag/replay/` already records and re-plays plans.
- Project rules already in force (must be respected by this task):
  - Default-off discipline with byte-equivalence proof for new flags.
  - Eval slice **named in PRD before `task.py start`**.
  - Vendor specifics live only in Appendix A with `as of` date.
  - Architecture v2 living doc: `.trellis/spec/backend/architecture.md`.
- Existing `Budget` and `PlanLog` are the natural state container for agent
  iterations — no need for a separate state machine store.

## Requirements (initial, will tighten during brainstorm)

- R1: A single config-level flag `rag.mode = classic | agentic` (default
  `classic`) plus per-request override.
- R2: When `mode = classic`, behavior is byte-equivalent to current main on the
  classic eval fixture (gate on diff = 0).
- R3: `agentic` mode runs as multiple steps inside the **same** `plan_id`, with
  every step appended to `PlanLog`. `replay/` must reproduce an agentic run.
- R4: `BudgetSpec` is extended with hard stops (`max_iterations`,
  `max_agent_tokens`, `max_tool_calls`); breach → graceful degrade to last
  classic answer + emit `agentic.budget_exhausted` event.
- R5: A new eval slice named explicitly in this PRD (TBD via brainstorm) covers
  the cases where agentic is expected to beat classic.
- R6: Observability: each agent step is one OTel span; metrics include
  iterations-per-query, tool-call counts, agentic-vs-classic latency and cost.
- R7: Provider verification (`production_provider_verify.py`) gains a hook for
  the agent decision LLM so the live-pilot path covers it.

## Acceptance Criteria

- [ ] AC1: With `rag.mode = classic` (default), the eval fixture produces a
      byte-equivalent answer set vs main.
- [ ] AC2: With `rag.mode = agentic` on the agentic eval slice (named below
      after brainstorm), end-to-end metric Δ meets the target also named below.
- [ ] AC3: `plan_log` for an agentic run contains ordered step records and
      `replay/` can reproduce the same final answer (within tolerance defined
      below).
- [ ] AC4: Budget breach is visibly traced and falls back without 5xx.
- [ ] AC5: Each child task ships flag-off and proves byte-equivalence at its
      own gate.

## Resolved Decisions

- **D1 (Q1) — MVP agentic flavors = A + B + C.**
  - **A. Adaptive** query classifier: LLM (or rule-based fast path) classifies
    each request into `no_retrieval | single_shot | multi_hop` and routes to
    the matching sub-pipeline. When `A == single_shot`, the agentic path must
    short-circuit to the classic pipeline so per-request byte-equivalence
    holds on simple queries.
  - **B. Iterative multi-hop**: bounded loop of `retrieve → grade →
    rewrite → retrieve`, capped by `BudgetSpec.max_iterations`. Includes a
    `RewriteTool` that reuses `queryplan/intent.py` and the existing
    rewrite-masking pipeline so PII rules stay intact.
  - **C. CRAG-lite grader**: each retrieval round is scored. **First-pass
    grader reuses the reranker dispatcher's score signal** (no extra LLM
    call) and only escalates to an optional LLM-judge when reranker scores
    are inconclusive (flag-gated, default off inside C itself).
  - **Excluded from MVP:** D (Self-RAG, reflection-token approach) and
    E (external tool-augmented: web/SQL/calculator). Both become follow-up
    parent tasks once MVP ships; E in particular waits until the current
    `live-pilot-provider-verification` line is stable.

- **D4 (Q4) — Eval slice names + AC2 gate (eval-as-driver: frozen now).**
  - **Four new JSONL slices**, all under `tests/fixtures/eval/`, sharing the
    existing `load_eval_suite` schema (one case per line, unique ids):
    - `agentic_simple_passthrough.jsonl` — simple single-shot questions; gate
      proves flavor A short-circuits to classic on these (byte-equivalent).
    - `agentic_multihop.jsonl` — genuine multi-hop questions where step-2
      query depends on step-1 evidence; covers flavor B.
    - `agentic_low_recall_recovery.jsonl` — first-pass retrieval is
      intentionally weak so flavor C's grader must trigger a rewrite + second
      retrieval; covers flavor C (and B's rewrite path).
    - `agentic_budget_breach.jsonl` — constructed to be unsolvable within
      `max_iterations`; gates the graceful-degrade path (R4).
  - **Reused existing slices, promoted into the agentic gate** (no new
    files, but new assertions):
    - `coffee.jsonl` / `realmanuals.jsonl` / `product_manuals.jsonl` under
      `mode=classic` must remain **byte-equivalent** to current main.
    - `cross_kb_negatives.jsonl` under `mode=agentic` must have a negative
      hit rate **no higher** than under `mode=classic` (no agentic-induced
      cross-KB bleed).
  - **AC2 gate (frozen)** — divided into hard MUST and target SHOULD:
    - **MUST** (failing any one fails AC2):
      1. `agentic_simple_passthrough.jsonl` byte-equivalent across modes.
      2. `agentic_budget_breach.jsonl`: 100% graceful degrade, zero 5xx,
         `agentic.budget_exhausted` event count equals case count.
      3. `cross_kb_negatives.jsonl`@agentic: negatives ≤ classic.
      4. All existing ranking slices @classic: byte-equivalent vs main.
    - **SHOULD** (the agentic win signal):
      1. `agentic_multihop.jsonl`: `hit@k` improvement ≥ +X over the
         per-slice baseline frozen in `tests/fixtures/eval/baselines/`.
      2. `agentic_low_recall_recovery.jsonl`: `recall@k` improvement ≥ +Y
         over the same baseline directory.
  - **No hard numeric thresholds in PRD.** X and Y are filled in only after
    the `agent-loop-driver` child task runs an honest baseline pass and
    writes `baselines/agentic_*.json`, with a documented confidence interval.
    Rationale: aligns with the project's "only port VCP, no calibration
    constants" memory and the known fixture-eval-ground-truth fragility —
    never let the gate be a guessed number.
  - **Out of MVP**: faithfulness / answer-quality LLM-judge metrics (e.g.
    RAGAS) and cost-per-correct-answer metrics. These wait for a follow-up
    task because they introduce new providers + new verification surface.

- **D2 (Q2) — Agent loop implementation = self-built.** Build a lightweight
  loop driver + tool registry on top of the existing `QueryPlan` / `PlanLog` /
  `BudgetGuard` / `answer/openai_compatible.py`. Do **not** adopt LangGraph
  or LlamaIndex AgentRunner. Rationale:
  - PlanLog is the single source of truth for `replay/`; introducing a
    framework checkpointer would create dual state and break R3.
  - Existing operational muscle (`BudgetGuard`, `circuit_breaker`,
    `calibration`, `chunk_identity`, `IndexGeneration`, `Wave`) does not map
    cleanly onto framework primitives.
  - Tool I/O schemas will mirror the OpenAI tool-calling format (and stay
    MCP-compatible), so a future swap to LangGraph stays a driver-only change.
  - Optional adapter: `wrap(LangChainTool)` may register external LangChain
    tools into our registry; this stays in `design.md` only, not MVP.

- **D3 (Q3) — Toggle granularity = global + per-request + eval-forced
  (no per-KB plane).**
  - **Global default** (`config.yaml: agentic.mode = classic`, default-off):
    add a new `AgenticConfig` pydantic model alongside `SearchConfig`,
    following the same shape and field-naming conventions.
  - **Per-request override**: extend `SearchRequest` (and `RetrieveRequest` /
    `AnswerRequest` where applicable) with `mode: Literal["classic","agentic"]
    | None = None` plus `agentic: AgenticOverrides | None = None`. Mirrors
    the existing T2 `budget: BudgetSpec | None` precedent.
  - **Eval / replay forced**: eval runner and `replay/` CLI accept
    `--force-mode classic|agentic`; the runner translates this into the
    per-request override path and stamps `plan.strategy["forced_mode"]` and a
    reason into `plan_log` so forced runs never contaminate organic A/B data.
  - **Resolution order** (codified in `design.md`): per-request override >
    eval force_mode > settings default.
  - **No per-KB plane in MVP.** Rationale: today `kb_name` is only a routing
    string and the repo has no per-KB config table; the only existing per-KB
    behavior switch is `QueryPlan.persist` (private-KB opt-out), which we
    reuse as a hard guard ("private KBs are forced classic"). Per-KB agentic
    selection can already be expressed by callers via the per-request
    override using their own `kb_name → mode` mapping. Building a per-KB
    config plane is deferred to a follow-up task.
- **D5 (Q5) — Agent decision LLM = dedicated `AgenticDecisionConfig` with
  explicit fallback to `AnswerConfig`.**
  - **New config block `AgenticDecisionConfig`** (mirrors `AnswerConfig`
    shape so ops are familiar):
    - `enabled: bool = False` (default-off discipline)
    - `provider: Literal["noop","openai_compatible"] = "noop"`
    - `model_id / base_url / api_key_env`: empty strings → **explicit
      fallback** to the corresponding `AnswerConfig` field.
    - `timeout_seconds: float = 15.0` (tighter than answer's 30s; decision
      calls are short).
    - `max_output_tokens: int = 256` (decision payload is small; protects
      budget).
    - `temperature: float = 0.0` (deterministic decisions help replay).
    - `tool_schema_mode: Literal["openai_tools","json_object"] =
      "openai_tools"` (default to OpenAI tools schema for MCP compatibility,
      per D2).
    - `json_strict: bool = True` (reject loose JSON to make replay stable).
  - **Factory `create_decision_generator(settings)`** lives next to
    `create_answer_generator`:
    - If `agentic.decision.enabled == False` **or** `model_id` is empty →
      wrap the existing answer generator into a `DecisionGenerator` adapter
      that caps `max_tokens` at the decision config's value. Single-provider
      ops keep working with zero extra config.
    - Otherwise → instantiate `OpenAICompatibleDecisionGenerator(cfg)`.
  - **Provider verification hook (satisfies R7)**:
    - `run_production_provider_verify` adds a `decision` step **only when**
      `agentic.mode != classic` **or** `agentic.decision.enabled == True`.
    - The smoke runs 1–2 frozen fixtures asserting the model returns
      strictly-parsable tool-call JSON (matching the registry schema);
      failure flips verify red.
    - `ProductionProviderVerifyReport` gains a `decision` section in
      `to_dict / to_json / to_markdown`.
  - **Why not reuse AnswerConfig directly (alt ①)**: answer models are
    typically chosen for citation fidelity (GPT-4-class) and are expensive
    + slow for tool selection; coupling also means an answer-model upgrade
    silently changes agent decisions, breaking flag-off byte-equivalence.
  - **Why not force a fully independent block (alt ②)**: would force
    single-provider deployments to maintain two provider blocks before they
    ever enable agentic; clashes with default-off ergonomics.
- **D6 (Q6) — Rerank dispatcher = zero-touch reuse; grader is a thin reader
  on top of `RerankResult.calibrated_score`.**
  - **Dispatcher API stays unchanged.** No `step_idx` field, no `grade_only`
    mode, no parallel grader service. Classic path is byte-equivalent because
    nothing in `reranker/dispatcher.py` is touched.
  - **Three-layer decision evidence** (codified here so each child task
    implements the same shape):
    1. **Raw facts** (from one `dispatcher.rerank(...)` call):
       `items[*].calibrated_score`, `vendor_used`, `cache_status`,
       `latency_ms`, `warnings`.
    2. **Three quantified signals** (`GradeOutcome`):
       - `top1_score = items[0].calibrated_score`
       - `margin = items[0].calibrated_score - items[1].calibrated_score`
       - `depth = #items with calibrated_score >= τ`
       - `signal ∈ {high, low, inconclusive, no_signal}` derived from the
         three numbers; `no_signal` is reserved for `cache_status=="skipped"`
         or `vendor_used=="noop"` so a budget-tight dispatcher result is
         never misread as "low quality".
    3. **Decision rules** (hard-coded fast path; decision LLM only as
       fallback):
       - step 0 → `retrieve`
       - `signal == high` and step ≥ 1 → `final`
       - `signal == low` and step < `max_iterations` → `rewrite`
       - `signal == low` and step == `max_iterations` → `abort` → triggers
         R4 graceful degrade
       - `signal == no_signal` → fall back to classic answer for this turn
         (no extra LLM spend on top of an already-tight budget)
       - **`signal == inconclusive`** → call `AgenticDecisionConfig` LLM
         with structured `GradeOutcome` + state; LLM returns a tool-call
         JSON conforming to the registry schema.
  - **Cache-key invariant (MUST preserve)**: dispatcher's cache key is
    `(plan, candidates)` and **must not start including `step_idx`**.
    Multi-round agent retrieves with different candidates re-hit the vendor
    (correct), and identical candidates legitimately re-hit cache (correct).
    A regression test in the agent-loop-driver child task locks this in
    place; commenting in `dispatcher.py` flags it as an agentic dependency.
  - **Per-step instruction injection (no API change)**: agent driver may
    write a different `plan.rerank["instruction"]` per step (e.g.
    `"first_pass_relevance"` vs `"post_rewrite_relevance"`); dispatcher
    already reads this field, so this is configuration, not code change.
  - **BudgetGuard sharing**: all dispatcher calls within one agent run
    share the same `BudgetGuard` instance, so `guard.remaining_ms()`
    naturally drains across iterations and dispatcher's own
    `reranker_skipped_due_to_budget` path becomes the upstream signal for
    `signal == no_signal` → graceful degrade.
  - **LLM-judge escalation**: only triggered when `signal == inconclusive`,
    flag-gated inside the C-flavor task, default off. LLM-judge **never
    produces a calibrated_score replacement**; it returns
    `relevant | irrelevant | partial` which the driver folds back into the
    `signal` field with provenance recorded in `plan_log`.
- **D7 (Q7) — Replay tolerance = schema equality + MUST-equality on key
  decision fields + Jaccard tolerance on evidence; LLM steps are trajectory
  replay, not re-generation.**
  - **Step-level verdict** (`StepReplayVerdict`):
    - MUST (any failure → step diverged):
      - `tool` exactly equal
      - `signal` exactly equal
      - `args` key-set equal (values not compared; LLM phrasing tolerated)
      - `decision_source` ("rule" vs "llm") equal
    - Tolerance (compared via existing `_jaccard`):
      - per-step `evidence_jaccard` between original and replayed
        `evidence_ids`
    - Informational only:
      - `rationale` is logged, never gates
  - **Run-level verdict** (`AgentRunReplayVerdict`):
    - MUST: `n_steps_orig == n_steps_replayed`
    - Reuses existing run metrics: `final_top1_match` (same field as
      `top1_stability`), `final_evidence_jaccard` (same field as
      `evidence_overlap_at_k`)
    - Three-tier outcome (mirrors current operational language):
      - `match`: all MUST pass + final Jaccard ≥ τ_high + top1 equal
      - `tolerated_drift`: all MUST pass + final Jaccard ∈ [τ_low, τ_high)
        — logged as a drift warning, replay still passes
      - `diverged`: any MUST fails → replay fails
  - **LLM-decision steps are trajectory replay, not re-generation.**
    When `decision_source == "llm"`, the replay driver reads the recorded
    `tool` + `args` from `plan_log.plan_steps` and executes the downstream
    tool directly — it never re-prompts the decision LLM. This mirrors the
    current `replay_plan` which also avoids re-calling the LLM and only
    re-runs the deterministic retrieval stack.
  - **Thresholds `τ_high` / `τ_low` are not hard-coded in PRD.** Default
    starting values (`τ_high = 0.95`, `τ_low = 0.80`) are filled into
    `tests/fixtures/eval/baselines/agentic_replay.json` only after the
    `agent-loop-driver` child task runs an honest baseline pass, with a
    documented confidence interval. Same discipline as D4.
  - **Reuses existing replay infrastructure** (zero new metric pipeline):
    - `_jaccard` from `replay/metrics.py`
    - `evidence_overlap_at_k` and `top1_stability` fields in
      `ReplayRunMetrics`
    - `latency_ms_p50 / p95` aggregation
    - Per-step extension is additive — classic `replay_plan` path remains
      byte-equivalent.
  - **Why not exact token equality (alt ①)**: incompatible with current
    replay philosophy, breaks the rolling 30-day plan store premise the
    moment a vendor upgrades a model, and aligns directly with the
    "fixture-eval-ground-truth fragility" caution already recorded in
    project memory.
  - **Why not pure schema equality (alt ②)**: leaves the decision tree
    unprotected — a code change that flips `signal==low → final` instead
    of `→ rewrite` would pass replay silently.
  - **Why not end-to-end answer equality only (alt ④)**: erases mid-trace
    visibility; replay can only say "answer differs" without telling you
    which step diverged, defeating the whole point of recording
    `plan_steps`.

## Planned Child Tasks (provisional, to be created after PRD freeze)

Dependencies must be written into each child's own `prd.md` / `implement.md`,
not implied by sibling order (per Trellis parent/child guidance).

1. **agent-loop-driver** — Self-built loop driver + tool registry +
   `plan_steps` schema; flag-off, must prove classic byte-equivalence.
2. **agentic-adaptive-router** — Flavor **A**: query classifier + router.
3. **agentic-iterative-multihop** — Flavor **B**: bounded retrieve/rewrite
   loop using the driver from #1.
4. **agentic-crag-grader** — Flavor **C**: reranker-signal-first grader with
   optional LLM-judge escalation behind its own flag.
5. **agentic-budget-and-fallback** — Extend `BudgetSpec`, breach handling,
   graceful degrade to last classic answer, classic-vs-agentic A/B gate.
6. **agentic-surface-and-provider-verify** — API / CLI / config wiring +
   hook agent decision LLM into `production_provider_verify.py`.

## Open Questions

_All Q1–Q7 resolved during brainstorm (see Resolved Decisions D1–D7).
No remaining blockers; proceeding to `design.md` and `implement.md`._

## Out of Scope (for this parent)

- Production rollout to all KBs (will gate on per-KB opt-in).
- Visual / OCR agentic flows (handled by `visual_retrieval/` separately).
- Cross-tenant agent collaboration / multi-agent.

## Notes

- This file holds requirements only. Technical design goes to `design.md`,
  execution checklist to `implement.md`, both required before `task.py start`
  because this is a complex task.
- Children will be created with
  `task.py create "<title>" --slug <name> --parent .trellis/tasks/05-21-agentic-rag-mode-toggle`
  once Q1–Q7 are resolved.
