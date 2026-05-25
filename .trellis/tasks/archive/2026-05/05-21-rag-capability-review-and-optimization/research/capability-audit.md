# Capability Audit

Date: 2026-05-21
Scope: audit-only parent. No production code changes.

## Executive Summary

TagMemoRAG now has a broad default-off RAG platform surface: ingestion,
chunking, hybrid retrieval, QueryPlan/PlanLog, replay, reranker dispatch,
evidence packs, `/answer`, provider verification, visual/OCR/connectors, and
agentic mode foundations. The biggest risk is no longer "missing any RAG
piece"; it is deciding which pieces are project-specific strengths and which
are maintenance-heavy custom infrastructure that mature libraries can cover.

Recommended posture:

- Keep custom: QueryPlan/PlanLog/replay, provider verification, privacy rules,
  WAVE/tag retrieval, evidence/citation contracts.
- Wrap rather than replace: LangChain/LlamaIndex loaders and splitters,
  retriever/tool adapters, optional evaluators.
- Defer broad runtime framework replacement until eval gates prove it.

## Evidence Inventory

### Implemented Surfaces

- Ingestion/parsing/chunking: `src/tagmemorag/parser.py` (894 lines), with
  Markdown/TXT/text-PDF handling, OCR hook, product-manual/generic profile,
  sentence/table-aware chunking.
- Retrieval: `src/tagmemorag/search_runtime.py` (353 lines) and
  `src/tagmemorag/retrieval.py` (578 lines), hybrid local vector, lexical,
  metadata narrowing, graph/WAVE, evidence/context pack.
- QueryPlan/replay: `src/tagmemorag/queryplan/` and `src/tagmemorag/replay/`,
  including SQLite plan log and replay runner.
- Reranker: `src/tagmemorag/reranker/dispatcher.py` (270 lines), vendor
  dispatch, calibration, cache, breaker, fallback.
- Answer: `src/tagmemorag/answer/`, optional default-off `/answer`, prompt and
  citation validation.
- Agentic: `src/tagmemorag/agentic/`, default-off loop driver, route, grade,
  replay, budget fallback, mode surface.
- Provider ops: `production_provider_smoke`, `production_provider_verify`,
  `provider_probe`, pilot/eval docs.

### Test and Eval Coverage

- Unit tests are broad: 100+ `tests/unit/test_*.py` files across parser,
  retrieval, eval, replay, reranker, provider verification, answer, visual,
  OCR, connectors, agentic.
- Eval fixtures are present but small:
  - classic/product slices: `coffee` 7, `product_manuals` 14,
    `realmanuals` 10, other classic slices 5 each.
  - agentic slices: 3 cases each.
- Recent full-suite result from prior parent: 1019 passed, 2 skipped.

## Axis-by-Axis Findings

| Axis | Current Strength | Gap/Risk | Recommendation |
|---|---|---|---|
| Ingestion/connectors | Registry/blob safety, fixture connector, PDF/TXT/MD | Common file/source loaders are custom and limited | Wrap mature loaders first; do not replace registry/blob model |
| Chunking | Structure-aware, sentence/table-aware, chunk identity protected | Custom code is large; semantic chunking absent | Compare LangChain/LlamaIndex splitters behind adapter |
| Indexing/storage | NPZ/Qdrant, generation paths, safe payloads | Qdrant only optional ANN; no vector-store abstraction for frameworks | Keep storage contracts; expose adapter if useful |
| Retrieval | Hybrid local vector+lexical+metadata+graph/WAVE | Ranking is complex and hard to compare to standard retrievers | Keep custom as differentiator; add adapter facade for tools/eval |
| Reranking | Dispatcher, calibration, breaker, fallback | Single external reranker family; no offline teacher workflow yet | Keep dispatcher; add eval/teacher child later |
| Evidence/context | Citation-aware `/retrieve`, context pack | Context packing/prompt budget policies need quality review | Audit prompt/context with answer-quality eval |
| Answer | OpenAI-compatible, citation validation, DeepSeek tested | Non-streaming only; quality/faithfulness metrics thin | Add groundedness/faithfulness eval child |
| Agentic | Replayable default-off MVP | Stub tools not productionized; metrics/spans limited | Child for production tool wiring after audit gates |
| Eval/replay | PlanLog replay, ranking fixtures, pilot docs | Eval cases small; answer quality metrics limited | Expand eval/diagnostics before optimizing ranking |
| Ops/provider | Strong smoke/verify/pilot path | Decision provider check local only; live decision smoke deferred | Child for live agentic provider verification |

## Project-Specific Invariants

These should be preserved unless a child task explicitly redesigns them:

- QueryPlan/PlanLog is the replay source of truth.
- Raw queries and raw document text are not leaked into logs/reports.
- Provider checks are explicit and env-gated.
- New behavior defaults off.
- Reranker/cache/key invariants are tested.
- WAVE/tag retrieval is a project differentiator, not a generic library
  feature.

## Highest-Leverage Gaps

1. **Library-assisted ingestion/chunking assessment.** Most likely place to
   reduce custom surface area safely.
2. **Eval/diagnostics upgrade.** Current ranking eval is useful but too small
   for confident optimization choices; answer faithfulness/groundedness is
   thin.
3. **Agentic production tool wiring.** Agentic surface exists, but production
   retrieve/final tool behavior needs explicit gates before enabling.
4. **Retriever/tool adapter boundary.** LangChain tools/retrievers can help
   integration if wrapped around existing contracts instead of replacing them.
5. **Prompt/context quality review.** Context assembly and answer prompts need
   measured citation/faithfulness review before more answer features.
