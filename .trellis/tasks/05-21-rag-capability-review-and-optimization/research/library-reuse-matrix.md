# Library Reuse Matrix

Date: 2026-05-21

## Sources Consulted

- LangChain retrieval docs: https://docs.langchain.com/oss/python/langchain/retrieval
- LangChain document loaders docs:
  https://docs.langchain.com/oss/python/integrations/document_loaders/index
- LangChain core API overview:
  https://api.python.langchain.com/en/latest/core/index.html
- LlamaIndex docs: https://docs.llamaindex.ai/
- LlamaIndex API reference: https://docs.llamaindex.ai/en/stable/api_reference/
- Haystack pipelines docs: https://docs.haystack.deepset.ai/v2.0/docs/pipelines
- Haystack components overview:
  https://docs.haystack.deepset.ai/v2.9/docs/components_overview
- Ragas metrics docs:
  https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/

## High-Level Fit

| Library | Best Fit for TagMemoRAG | Main Risk |
|---|---|---|
| LangChain | Loaders, text splitters, retriever/tool adapters, simple runnable wrappers | Dependency churn and abstractions competing with QueryPlan/PlanLog |
| LlamaIndex | Document ingestion/index/query experiments, node parsing comparison | Replacing storage/query engine would duplicate existing index/replay stack |
| Haystack | Typed component pipeline ideas and possible offline pipeline prototypes | Pipeline graph may duplicate existing explicit Python orchestration |
| Ragas | Optional answer/retrieval faithfulness and relevance diagnostics | LLM-judge cost, provider variance, metric opacity |

## Decision Matrix

| Area | Current Custom Code | Library Candidate | Decision | Rationale |
|---|---|---|---|---|
| Common loaders | Parser/connectors are project-owned | LangChain loaders, LlamaIndex readers | Wrap | Good reuse for DOCX/HTML/Notion-like sources; preserve registry/blob metadata |
| Text splitting | `parser.py` custom split/merge/table logic | LangChain text splitters, LlamaIndex node parsers | Compare behind adapter | Current chunk identity and table/page metadata are valuable; replace only with eval evidence |
| Vector store | NPZ/Qdrant custom adapters | LangChain vector stores, LlamaIndex stores | Keep custom | Existing generation, safe payload, and replay contracts are project-specific |
| Retrieval | `execute_search`, WAVE/tag/lexical/metadata | LangChain retriever interface, Haystack retriever component | Wrap | Expose existing retriever as library-compatible object; do not replace ranking |
| Reranking | Dispatcher/calibration/cache/breaker | Library reranker wrappers | Keep custom | Current dispatcher owns provider policy and safety; library wrappers add little |
| Prompt assembly | Custom context pack/prompt | LangChain PromptTemplate, Haystack PromptBuilder | Defer/wrap lightly | Prompt template abstraction is not the hard part; citation validation is custom |
| Agent tools | Custom AgentToolRegistry | LangChain tools | Wrap | Tool schema compatibility already exists; adapter is low-risk and useful |
| Agent orchestration | Custom replayable driver | LangGraph/LangChain agents, Haystack agents | Defer | Prior ADR chose self-built loop to preserve PlanLog ownership |
| Eval | Custom ranking eval/replay | Ragas, DeepEval-like tooling | Add optional diagnostics | Strong value for faithfulness/groundedness if env-gated and non-blocking first |
| Pipelines | Explicit Python flow | Haystack pipelines | Defer | Useful as design reference; runtime replacement not justified yet |

## Recommended Child Decisions

1. **LangChain loader/splitter adapter spike** — add optional dependency and
   compare loader/splitter output against current parser on fixtures.
2. **RAG diagnostics evaluator spike** — add optional Ragas-like diagnostics
   for `/answer` reports, initially offline and non-blocking.
3. **LangChain retriever/tool adapter** — expose TagMemoRAG retrieval and
   agent tools through LangChain-compatible interfaces without changing
   runtime execution.

## Non-Recommendations

- Do not replace QueryPlan/PlanLog with LangChain memory/checkpoints.
- Do not replace Qdrant/NPZ storage with framework vector-store abstractions.
- Do not replace WAVE/tag ranking without eval proof.
- Do not add framework dependencies to the base install before proving an
  adapter use case.
