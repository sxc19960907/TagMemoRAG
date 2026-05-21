# RAG Capability Review and Optimization

## Goal

Reassess TagMemoRAG's end-to-end RAG capability after the default-off
agentic MVP. The parent task should identify the highest-leverage gaps,
decide where mature frameworks/libraries such as LangChain should replace or
wrap custom code, and produce an implementation roadmap with eval gates before
any broad refactor starts.

## User Value

- Avoid spending more engineering time rebuilding common RAG infrastructure
  that mature libraries already cover well.
- Keep project-specific strengths, especially QueryPlan/PlanLog replay,
  WAVE/tag retrieval, provider verification, and product-manual evidence.
- Move from "many MVP features exist" to a clearer capability model:
  what works, what is weak, and what should be improved first.

## Confirmed Facts

- Current branch has no active Trellis tasks and a clean worktree before this
  parent was created.
- The previous parent `agentic-rag-mode-toggle` is archived; C1-C6 shipped
  default-off agentic loop foundation, router, iterative loop, CRAG-lite
  grader, budget fallback, public mode surface, and provider verify decision
  check.
- `pyproject.toml` currently does **not** include LangChain, LlamaIndex, or
  Haystack dependencies.
- Existing RAG surface includes:
  - parser/chunker for Markdown, TXT, and text PDFs;
  - local NPZ and optional Qdrant vector storage;
  - hybrid vector/lexical/metadata/graph retrieval;
  - first-class reranker dispatcher;
  - evidence-aware `/retrieve`;
  - optional `/answer`;
  - QueryPlan/PlanLog/replay;
  - visual retrieval, OCR, connectors, and agentic mode foundations.
- Existing eval fixtures include classic slices plus new agentic slices under
  `tests/fixtures/eval/`.
- Architecture doc still states the project is a working retrieval foundation,
  not a complete production RAG platform.

## Requirements

- **R1 — Capability audit.** Produce a structured audit of ingestion,
  chunking, indexing, retrieval, reranking, context assembly, answer
  generation, agentic orchestration, eval/replay, provider verification,
  observability, and operations.
- **R2 — Library reuse matrix.** Compare custom implementations against
  mature alternatives, with a first-class look at LangChain. For each area,
  decide one of: keep custom, wrap with adapter, replace, or defer.
- **R3 — No framework-driven rewrite.** Preserve project-specific contracts
  unless a child task proves a replacement is better: QueryPlan/PlanLog,
  replayability, privacy rules, provider verification, and default-off
  discipline.
- **R4 — Eval-first optimization roadmap.** Every proposed optimization must
  name a measurable gate: eval fixture, replay metric, live provider smoke, or
  bounded benchmark.
- **R5 — Child task map.** Split follow-up work into independently
  verifiable child tasks, ordered by risk and leverage.
- **R6 — Dependency discipline.** Adding LangChain or any framework requires a
  scoped child task, dependency update, tests, and rollback plan.
- **R7 — Documentation honesty.** The output must clearly separate shipped
  capability, known gaps, and future options.
- **R8 — Audit-only scope.** This parent does not implement production code.
  It may create documentation, research artifacts, and child task plans only.

## Acceptance Criteria

- [x] **AC1 — Audit artifact.** Parent includes or links a capability audit
      that names strengths, gaps, risks, and evidence from code/tests/docs.
- [x] **AC2 — Reuse decision matrix.** LangChain and at least two other
      mature RAG/library options are assessed against project constraints.
- [x] **AC3 — Child roadmap.** Parent has a child task list with scope,
      ordering, gates, and rollback notes.
- [x] **AC4 — No premature implementation.** No production code is changed in
      this parent before the audit and roadmap are reviewed.
- [x] **AC5 — Eval gates named.** Each recommended child task names concrete
      tests/eval slices or provider verification commands.
- [x] **AC6 — User decision recorded.** The parent records whether this round
      is audit-only or audit-plus-implementation.
- [x] **AC7 — Production code untouched.** Parent completion has no diff under
      `src/` or runtime tests except audit artifacts and task docs.

## Research Outputs

- `research/capability-audit.md`
- `research/library-reuse-matrix.md`
- `research/child-roadmap.md`

## Child Roadmap Created

1. `05-21-langchain-loader-splitter-adapter`
2. `05-21-rag-answer-quality-diagnostics`
3. `05-21-langchain-retriever-tool-adapter`
4. `05-21-agentic-production-tool-wiring`
5. `05-21-prompt-context-pack-quality-review`

## Initial Candidate Workstreams

These are hypotheses to validate during planning, not approved child tasks yet:

1. **Document ingestion and chunking reuse.** Evaluate whether LangChain
   loaders/splitters help for DOCX/HTML/PDF while preserving current chunk
   identity and metadata contracts.
2. **Retriever abstraction.** Evaluate adapter boundaries for LangChain
   retrievers/tools without replacing QueryPlan/PlanLog.
3. **Eval and quality diagnostics.** Strengthen answer/retrieval quality
   measurement beyond current ranking fixtures, possibly with optional
   faithfulness/groundedness checks.
4. **Agentic productionization.** Replace stub tools with production
   retrieval/final tools only after capability gates are explicit.
5. **Prompt/context assembly.** Review context pack and answer prompt against
   common RAG prompt patterns and citation failure modes.

## Out of Scope

- Immediate large-scale rewrite to LangChain/LlamaIndex/Haystack.
- Adding live paid-provider tests without an explicit child task and safe env
  gating.
- Removing WAVE/tag retrieval without eval evidence.
- Changing public API contracts before a migration plan exists.

## Open Questions

- Q1 resolved 2026-05-21: user chose **audit-only**. Do not implement the
  first optimizations in this parent; create child tasks for later execution.
