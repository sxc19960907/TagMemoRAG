# Agentic RAG Mode Toggle — Execution Plan

> Companion to `prd.md` and `design.md`. PRD owns "what / why / accept";
> design owns "how it fits"; this file owns "what to do, in what order,
> and how to validate at each gate". Decisions cited as Dn correspond to
> PRD Resolved Decisions D1–D7.

## 0. Operating Rules for This Parent Task

- **Parent task does no implementation directly.** All code lands inside
  child tasks; this `implement.md` orchestrates child creation, ordering,
  cross-child checks, and final integration review.
- **Default-off discipline applies at every child boundary.** A child
  cannot land unless its slice of AC1/AC5 (classic byte-equivalence) is
  green and its slice of AC2 MUST gate (D4) is green.
- **Eval-as-driver discipline applies at every child boundary.** Each
  child names the eval slices it's gated on in its own `prd.md`.
- **Per-child sub-agent dispatch**: when a child is `in_progress`, dispatch
  prompt starts with `Active task: <child path from task.py current>`.

## 1. Pre-Flight Review (before `task.py start` on this parent)

Gate items the user must confirm before this parent's planning is closed:

- [ ] PRD frozen with D1–D7 (verified: 7 decisions present, 0 open
      questions remaining).
- [ ] `design.md` reviewed: contracts in §3 match D1–D7.
- [ ] `implement.md` (this file) reviewed: ordering and gates acceptable.
- [ ] Branch / base-branch decision recorded via `task.py set-branch`
      (suggested: a long-lived integration branch
      `agentic-rag-mode-toggle`, with each child branching from it).
- [ ] Confirm: do we want to keep PRD-only at parent and let each child
      own its own `design.md` + `implement.md`? (Recommended: yes; see §3.)

## 2. Child-Task Creation Sequence (after parent `task.py start`)

Run from repo root. Each `task.py create` returns a `MM-DD-<slug>`
directory; capture and persist into the parent's child list.

```bash
PARENT=.trellis/tasks/05-21-agentic-rag-mode-toggle

# C1 — foundation
python3 ./.trellis/scripts/task.py create "Agentic Loop Driver and Plan Steps" \
  --slug agent-loop-driver --priority P1 --parent "$PARENT" \
  --description "Self-built loop driver, AgentTool registry, plan_steps table, budget extension. Flag-off; classic byte-equivalent."

# C2 — flavor A
python3 ./.trellis/scripts/task.py create "Agentic Adaptive Router" \
  --slug agentic-adaptive-router --priority P1 --parent "$PARENT" \
  --description "Flavor A: classify request as no_retrieval/single_shot/multi_hop and short-circuit single_shot to classic for byte-equivalence."

# C3 — flavor B
python3 ./.trellis/scripts/task.py create "Agentic Iterative Multi-hop" \
  --slug agentic-iterative-multihop --priority P1 --parent "$PARENT" \
  --description "Flavor B: bounded retrieve→grade→rewrite→retrieve loop using the driver. Reuses queryplan/intent.py for rewrites."

# C4 — flavor C
python3 ./.trellis/scripts/task.py create "Agentic CRAG-lite Grader" \
  --slug agentic-crag-grader --priority P1 --parent "$PARENT" \
  --description "Flavor C: GradeOutcome derived from RerankResult.calibrated_score; optional LLM-judge escalation behind its own flag (default off)."

# C5 — budget / fallback
python3 ./.trellis/scripts/task.py create "Agentic Budget and Fallback" \
  --slug agentic-budget-and-fallback --priority P1 --parent "$PARENT" \
  --description "Extend BudgetSpec with max_iterations/max_agent_tokens/max_tool_calls; graceful degrade to classic on breach; AC4 + classic-vs-agentic A/B gate."

# C6 — surface + provider verify
python3 ./.trellis/scripts/task.py create "Agentic Surface and Provider Verify" \
  --slug agentic-surface-and-provider-verify --priority P1 --parent "$PARENT" \
  --description "API/CLI/config wiring, AgenticConfig + AgenticDecisionConfig + per-request override; hook decision LLM into production_provider_verify."
```

After creation, verify links:

```bash
python3 ./.trellis/scripts/task.py list --mine
ls "$PARENT" && cat "$PARENT/task.json" | grep -A 20 children
```

## 3. Child Artifact Setup (every child)

Each child is a **complex sub-task** (touches multiple modules + has its
own gate). Therefore each child must own:

- `prd.md` — slice-specific requirements + acceptance criteria + named
  eval slices it gates on.
- `design.md` — slice-specific contracts (e.g. `AgentToolRegistry` API
  for C1; `Router` interface for C2).
- `implement.md` — slice-specific checklist with validation commands.
- `implement.jsonl` / `check.jsonl` — spec/research manifests for
  sub-agent context.
- Cross-child dependencies declared explicitly inside the child's own
  `prd.md` (per Trellis parent/child guidance: dependencies are not
  implied by tree position).

## 4. Implementation Order & Gates

```
[C1] agent-loop-driver
   ├── lands plan_steps schema, driver, registry, budget extension
   ├── classic eval byte-equivalent (AC1)
   └── runs honest baseline pass on agentic_simple_passthrough.jsonl
       agentic_multihop.jsonl agentic_low_recall_recovery.jsonl
       and writes baselines/agentic_*.json (D4 deferred thresholds).
        ↓
[C2] agentic-adaptive-router    [parallel-ok with C3 once C1 lands]
   ├── flavor A behind agentic.enabled_flavors=[adaptive]
   ├── single_shot path proves byte-equivalent vs classic on
   │   agentic_simple_passthrough.jsonl (D4 MUST 1)
   └── classic gate untouched.
        ↓
[C3] agentic-iterative-multihop
   ├── flavor B behind agentic.enabled_flavors=[..., iterative]
   ├── proves SHOULD signal on agentic_multihop.jsonl using
   │   baselines from C1.
   └── reuses queryplan/intent.py rewrite path.
        ↓
[C4] agentic-crag-grader
   ├── flavor C behind agentic.enabled_flavors=[..., crag]
   ├── reuses RerankerDispatcher.rerank zero-touch (D6 invariant test)
   ├── crag_llm_judge_enabled remains False by default
   └── proves SHOULD signal on agentic_low_recall_recovery.jsonl.
        ↓
[C5] agentic-budget-and-fallback
   ├── BudgetSpec.max_iterations / max_agent_tokens / max_tool_calls
   ├── private-KB hard guard (D3)
   ├── 100% graceful degrade on agentic_budget_breach.jsonl (D4 MUST 2)
   └── cross_kb_negatives.jsonl@agentic ≤ classic (D4 MUST 3).
        ↓
[C6] agentic-surface-and-provider-verify
   ├── AgenticConfig / AgenticDecisionConfig wired into Settings
   ├── SearchRequest / RetrieveRequest / AnswerRequest accept
   │   per-request mode + agentic overrides
   ├── eval/replay CLI accepts --force-mode
   ├── production_provider_verify gains conditional decision step (D5)
   └── AC1 + AC2 MUST gates fully green at parent level.
```

Each arrow is a hard sequencing gate: the next child cannot start until
the previous child's MUST-class checks are green.

## 5. Validation Commands (by child)

These are reference commands; each child's own `implement.md` will
expand them with arguments:

```bash
# Static checks (every child, every commit)
ruff check src tests
mypy src/tagmemorag

# Unit + integration
pytest tests/unit -q
pytest tests/integration -q -k agentic

# Eval gate (per child)
python3 -m tagmemorag.eval.runner \
  --suite tests/fixtures/eval/<slice>.jsonl \
  --baseline tests/fixtures/eval/baselines/<slice>.json

# Classic byte-equivalence regression
python3 -m tagmemorag.eval.runner \
  --suite tests/fixtures/eval/coffee.jsonl \
  --suite tests/fixtures/eval/realmanuals.jsonl \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --force-mode classic --diff-against main

# Provider verify (C6 specifically; runs decision step when applicable)
python3 -m tagmemorag.cli production-provider-verify \
  --report-dir data/_global/verify_reports
```

## 6. Risky Files & Rollback Points

| Path | Risk | Rollback |
|---|---|---|
| `src/tagmemorag/queryplan/plan_log.py` | Schema additive; if `plan_steps` rolls out malformed, classic plans still write fine | Drop `plan_steps` table; runtime feature disabled; classic continues |
| `src/tagmemorag/api.py` | Request schema additive | Revert request fields; classic clients unaffected |
| `src/tagmemorag/reranker/dispatcher.py` | **Must NOT change** (D6) | Any diff to this file rejects review |
| `src/tagmemorag/answer/openai_compatible.py` | **Must NOT change** (D5 wraps from outside) | Same |
| `src/tagmemorag/agentic/*` | New code; isolated | Delete package; remove imports; classic continues |
| `tests/fixtures/eval/agentic_*.jsonl` | New fixtures | Remove files; existing slices unchanged |
| `tests/fixtures/eval/baselines/agentic_*.json` | Baseline numbers | Re-run baseline pass; commit new file |

Per-child rollback: a child branch can be dropped without affecting
others, because each child gates on classic byte-equivalence
independently.

## 7. Exit Criteria for Parent

The parent task moves to `completed` only when **all** are true:

- [x] All six children archived green.
- [x] Parent-level eval gate passes (D4: AC1 + AC2 MUST + cross-slice
      regressions).
- [x] D6 invariant test (`dispatcher cache key independent of step_idx`)
      lives in `tests/unit` and is green.
- [x] D7 replay verdict: `agentic_*` fixtures replay as `match` or
      `tolerated_drift`; zero `diverged` on baseline.
- [x] `production_provider_verify` runs include the decision step when
      `agentic.mode != classic` or `agentic.decision.enabled == True`.
- [x] Spec update committed (Phase 3.3): `agentic` package documented in
      `.trellis/spec/backend/architecture.md`; ADR for D2 (self-built
      loop choice) created via `manage_adr`.

## 9. Final Validation Results

- C1 committed: `2340ca4c51c59e4935db1a0fc1bf49e176553bea`.
- C2 committed: `d3b1e53a3d13e3335bc8d26ac0ba6e2921ff496e`.
- C3 committed: `0270af9c144d9be47430276552eb644e3f4e05c8`.
- C4 committed: `3ea8eafb33e6241d9fea42d3363f7a523c98315a`.
- C5 committed: `7ddff0b7f6a9bd522d4e4bf3f5a736722964ce56`.
- C6 committed: `e9cb01232a7bd4a7baa6edaeeaf96d90b079e706`.
- Final C6 integration gate: 115 passed.
- Eval CLI e2e: 3 passed.
- Full suite: 1019 passed, 2 skipped.
- `git diff --check` passed.

Follow-up note: the original PRD's broader quality-improvement ambition is
now separated from this MVP. The next parent should reassess RAG capability
end-to-end, including where LangChain or other libraries can replace custom
code, rather than expanding this mode-toggle task further.

## 8. Pre-`task.py start` Checklist (this parent)

- [x] `prd.md` finalized: D1–D7 + child task topology + AC1–AC5.
- [x] `design.md` written: §1–§7 covered.
- [x] `implement.md` written: this file.
- [ ] User reviews and approves planning artifacts.
- [ ] Branch decision recorded.
- [ ] Curate parent's `implement.jsonl` + `check.jsonl` only if a sub-agent
      will run on the **parent** (none planned in MVP — children own their
      own jsonl).

Once the user approves: run

```bash
python3 ./.trellis/scripts/task.py start .trellis/tasks/05-21-agentic-rag-mode-toggle
```

then proceed to §2 child-task creation.
