# RAG Capability Review and Optimization — Design

## Scope

This parent is an audit and planning task. It produces structured research,
decision records, and child task definitions. It does not change production
code. Any implementation suggested by the audit must become a child task with
its own PRD, design, implementation plan, validation commands, and rollback
plan.

## Audit Axes

The audit should cover the full RAG path:

1. Ingestion and connectors
2. Parsing and chunking
3. Chunk identity and index generation
4. Embeddings and vector storage
5. Retrieval, metadata narrowing, graph/WAVE, lexical search
6. Reranking and calibration
7. Evidence and context assembly
8. Answer generation and citation validation
9. Agentic orchestration
10. Eval, replay, feedback, and diagnostics
11. Provider verification and deployment operations
12. Observability and failure handling

Each axis should record:

- current implementation and owning modules;
- tests/eval fixtures that cover it;
- known gaps and operational risks;
- whether mature libraries can help;
- recommended decision: keep custom, wrap, replace, or defer.

## Library/Framework Comparison

At minimum compare:

- LangChain: loaders, text splitters, retrievers, tools, LCEL/runnables,
  evaluators.
- LlamaIndex: document loaders, node parsers, retriever/query-engine patterns,
  eval tooling.
- Haystack or RAGAS/DeepEval class tooling: focus on eval/diagnostics rather
  than runtime replacement if appropriate.

Frameworks are assessed against TagMemoRAG invariants:

- QueryPlan/PlanLog remains the replay source of truth.
- Raw query/text/privacy rules are preserved.
- Provider verification stays explicit and environment-gated.
- Classic/default-off behavior remains stable.
- Eval gates are named before implementation.

## Outputs

This parent should produce:

- `research/capability-audit.md`
- `research/library-reuse-matrix.md`
- `research/child-roadmap.md`
- child Trellis task directories for the approved roadmap, kept in planning
  status unless the user explicitly asks to start implementation.

## Compatibility

Because this parent is audit-only, compatibility is enforced by absence of
runtime diffs. The final check should show no production code changes under
`src/`.

## Rollback

Rollback is documentation-only: remove or revise research artifacts and child
task plans. No runtime migrations are allowed in this parent.
