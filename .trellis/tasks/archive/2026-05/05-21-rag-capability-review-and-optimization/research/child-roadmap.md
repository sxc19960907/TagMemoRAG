# Child Roadmap

Date: 2026-05-21
Parent scope: audit-only. Child tasks should be created in planning status
and started only after user approval.

## Recommended Order

### C1 — LangChain Loader and Splitter Adapter Spike

Goal: Evaluate whether LangChain loaders/text splitters reduce custom ingestion
and chunking burden without breaking chunk identity, metadata, table/page
semantics, or eval baselines.

Scope:

- Optional dependency only, likely extra `langchain`.
- Adapter converts LangChain `Document` objects into existing parser/chunk
  intermediate shape.
- Compare current parser/chunker vs LangChain-backed path on MD/TXT/PDF and
  any DOCX/HTML fixture added by the child.

Gates:

- Parser/chunker unit tests.
- `tests/fixtures/eval/product_manuals.jsonl`.
- `tests/fixtures/eval/coffee.jsonl`.
- No raw text leak in debug/log artifacts.

Rollback:

- Remove optional dependency and adapter; current parser remains default.

### C2 — RAG Answer Quality Diagnostics

Goal: Add optional offline diagnostics for answer faithfulness, context
relevance, and response relevance.

Scope:

- Evaluate Ragas or similar tooling.
- Keep diagnostics offline / non-blocking by default.
- Produce bounded JSON report from existing eval or replay outputs.

Gates:

- Existing answer API tests.
- New fixture with grounded and ungrounded answers.
- Provider/env-gated tests with fake judge by default.

Rollback:

- Remove diagnostics command/extra dependency; ranking eval remains unchanged.

### C3 — LangChain Retriever and Tool Adapter

Goal: Expose TagMemoRAG retrieval and agent tools through LangChain-compatible
interfaces while keeping QueryPlan/PlanLog as source of truth.

Scope:

- Adapter around existing `/retrieve` or internal retrieval function.
- Adapter around `AgentToolRegistry` schemas.
- No runtime switch to LangChain agents.

Gates:

- QueryPlan rows still written.
- Replay still works.
- Agentic tool registry tests.
- No change to classic retrieval output.

Rollback:

- Delete adapter package and optional dependency.

### C4 — Agentic Production Tool Wiring

Goal: Replace or augment C1-C6 agentic stub tools with production retrieval and
final-answer behavior under explicit eval gates.

Scope:

- Use existing retrieval/answer generator contracts.
- Keep private-KB and budget fallback from C5.
- Do not enable by default.

Gates:

- `agentic_simple_passthrough.jsonl`.
- `agentic_multihop.jsonl`.
- `agentic_low_recall_recovery.jsonl`.
- `agentic_budget_breach.jsonl`.
- full replay verdict tests.

Rollback:

- Disable agentic mode; stub tools remain test baseline.

### C5 — Prompt and Context Pack Quality Review

Goal: Improve context packing and answer prompt quality based on diagnostics,
not taste.

Scope:

- Review context item ordering, citation density, prompt instructions, and
  answer refusal behavior.
- Add fixture cases for citation misses and conflicting evidence.

Gates:

- answer prompt tests.
- answer API tests.
- diagnostics report from C2 if available.
- DeepSeek provider smoke when env is available.

Rollback:

- Revert prompt/context changes; retrieval output remains unchanged.

## Deferred

- Full runtime migration to LangGraph/LlamaIndex/Haystack.
- Replacing WAVE/tag retrieval.
- Per-document ACL and multi-tenant permissions.
- Paid live-eval gates without explicit env and cost controls.
