# General RAG platform metadata narrowing

## Goal

Move TagMemoRAG from a product-manual-shaped RAG system toward a general RAG platform by introducing a generic document metadata layer and query-time metadata narrowing. Product manuals remain the first supported domain schema, but search should no longer depend on every document being a device manual or on operators manually passing filters.

The immediate production need is clear from the real PDF manual eval: when the user query contains an exact model / brand / category signal, retrieval should narrow the candidate set before vector / lexical / wave ranking. A query like `HR6FDFF701SW 制冰机怎么设置` should search the matching Hisense refrigerator manual first, not all washer / dryer / oven / refrigerator chunks.

## Background / Known Context

- The archived `05-17-pdf-manual-real-eval` task found that real PDF manual retrieval is contaminated by cross-product chunks.
- Four-config routing diagnostic results were identical: `vec-only`, `wave-baseline`, `wave-residuals`, and `wave-resonance` all had top1 category hit `0.667`, top5 category hit `0.917`, and mrr_cat `0.778`.
- The primary bottleneck was not algorithm flags; it was broad candidate scope plus weak PDF structure.
- User direction: product model and vendor should be usable as tags / filters so search can compress to the correct manual instead of “大海捞针”.
- User direction: the project should become a general RAG platform, not only a device manual RAG.
- SiliconFlow production text embedder target is now `Qwen/Qwen3-Embedding-8B` (4096 dim), which fits the general RAG direction better than the previous VL-targeted model.

## Current Architecture Facts

- Generic foundations already exist:
  - `kb_name` is threaded through build, search, storage, API, and eval.
  - Embedding providers are configurable: local, hashing, OpenAI-compatible HTTP.
  - Storage has local JSON/NPZ and optional Qdrant vector backend.
  - Search already supports explicit filters through `SearchFilters` / CLI flags / `filter_node_ids`.
  - Graph nodes already carry arbitrary `metadata` in addition to manual-specific top-level fields.
- Product-manual coupling still exists:
  - Metadata contract is `ManualMetadata` in `src/tagmemorag/manuals.py` with fields like `manual_id`, `product_category`, and `product_model`.
  - Result shape exposes `manual_id`, `manual_title`, `brand`, `product_category`, `product_model` directly.
  - `/manuals`, manual registry, manual library, bundle, and upload APIs are named around manuals.
  - Search filters only know fixed fields: `manual_id`, `brand`, `product_category`, `product_model`, `language`, and `tags`.
  - There is no query-time entity extraction / narrowing step; users must pass filters manually.

## Problem

The system has a strong retrieval core but lacks a platform-level metadata abstraction. Today, domain identity is either embedded in manual-specific fields or left as unstructured tags. This causes two problems:

1. Product manuals cannot reliably use model / brand / category identity unless callers manually pass filters.
2. Future domains (legal docs, research papers, code docs, CRM notes, support tickets, policies, medical records, etc.) would either have to abuse manual fields or require new one-off code paths.

## Product Direction

Introduce a domain-neutral metadata and narrowing layer:

- **Document identity**: stable document id, title, source file, domain, document type, language, status, tags, and arbitrary attributes.
- **Domain schemas**: optional adapters that map domain-specific fields into generic metadata.
- **Product manual schema**: first adapter, mapping brand/model/category/manual_id into generic fields and search aliases.
- **Query narrowing**: automatically infer high-confidence filters from query text and KB metadata indexes before ranking.
- **Progressive confidence**: hard-filter only exact / high-confidence entity matches; boost or leave global search for ambiguous signals.

## Requirements

### R1 Generic document metadata model

- Add a domain-neutral metadata representation that can describe any document type.
- Required common fields should include:
  - `doc_id`
  - `title`
  - `source_file`
  - `domain`
  - `doc_type`
  - `language`
  - `status`
  - `tags`
  - `attributes` (arbitrary string/list scalar metadata)
- The existing product manual fields must remain load-compatible.
- Existing sidecars must continue to build without migration.

### R2 Product manual schema adapter

- Map existing manual sidecar fields into generic metadata:
  - `manual_id` -> `doc_id` and `attributes.manual_id`
  - `brand` -> `attributes.brand` plus normalized alias/tag
  - `product_category` -> `attributes.product_category` plus normalized alias/tag
  - `product_model` -> `attributes.product_model` plus normalized alias/tag
  - `title`, `source_file`, `language`, `status`, `tags` remain common fields
- Preserve current API result fields for backward compatibility.
- Add identity tags for chunks where appropriate:
  - `brand:<brand>`
  - `model:<model>`
  - `category:<category>`
  - `doc:<doc_id>` or `manual:<manual_id>` for manual schema

### R3 Metadata index for narrowing

- Build an in-memory per-KB metadata index from loaded graph nodes.
- Index must support exact and normalized lookup for:
  - common `doc_id`, `domain`, `doc_type`, `language`, `tags`
  - schema attributes such as `brand`, `product_model`, `product_category`
- Index must deduplicate values and map them to eligible node ids / document ids.
- Index construction must not require external services.

### R4 Query-time metadata narrowing

- Add a search pre-processing step that inspects the query and metadata index.
- For product manuals, detect:
  - exact product model tokens such as `HR6FDFF701SW`, `DHGA901NL`, `W6564`
  - brand names such as `Hisense`, `ASKO`
  - product category terms / aliases such as `冰箱`, `refrigerator`, `dryer`, `洗衣机`
- High-confidence exact model match should hard-filter to matching document(s).
- Brand-only or category-only matches should be configurable as hard-filter or boost; MVP recommendation is:
  - model: hard filter
  - brand + category together: hard filter
  - category only: hard filter for product-manual KBs, boost for generic KBs
  - brand only: boost by default unless unique in KB
- When no high-confidence signal exists, retrieval must behave exactly as it does today.

### R5 Generic filter API compatibility

- Existing search request filters must keep working.
- Add a generic filter shape for future domains, for example `metadata_filters` / `attributes` / `facets` (final naming in design).
- API and CLI should expose auto-narrowing diagnostics when `debug=true` / `--debug-search`:
  - detected entities
  - inferred filters
  - confidence / rule
  - hard-filter vs boost decision
  - candidate count before/after narrowing

### R6 Evaluation

- Add tests and eval cases proving that model/brand/category narrowing improves realmanuals-style retrieval.
- Existing hashing CI must remain green.
- The new behavior must include regression tests for ambiguous matches and no-match fallback.

### R7 General platform guardrails

- Do not rename every manual API in this task.
- Do not break existing product manual management flows.
- Do not introduce an LLM dependency for query understanding in MVP.
- Do not make domain-specific logic leak into the core wave algorithm.

## Non-Functional Requirements

- Backward compatible with existing sidecars and saved KB artifacts where feasible.
- Deterministic and offline-testable.
- Minimal latency overhead: metadata narrowing should be local and cheap.
- Safe debug metadata: no raw document snippets or secrets in logs/metrics/cache keys.
- Configurable enough for future domains without rewriting search internals.

## Acceptance Criteria

- [ ] Existing product manual sidecars still build and search successfully.
- [ ] Generic metadata representation exists and is documented.
- [ ] Product manual metadata adapter maps brand/model/category/manual_id into generic attributes and identity tags.
- [ ] Query-time narrowing detects exact product models and narrows search to matching manual chunks.
- [ ] Category/brand narrowing behavior is implemented according to confidence rules and configurable where needed.
- [ ] `/search` and CLI search can report narrowing diagnostics in debug mode.
- [ ] Existing explicit filters remain backward compatible.
- [ ] New unit tests cover metadata normalization, index lookup, entity detection, narrowing decisions, and fallback behavior.
- [ ] New eval/regression cases show improved top1/top5 routing on realmanuals-style queries.
- [ ] `.venv/bin/python -m pytest tests/ -q` passes.
- [ ] `.venv/bin/python scripts/run_eval_ci.py` passes.

## Out of Scope

- Full UI redesign or renaming `/manuals` to `/documents`.
- LLM-based query parsing.
- Full PDF section-aware extraction (separate task, still important).
- Multi-tenant auth redesign.
- Migrating all existing persisted data to a new schema in one step.
- General ontology management UI.

## Open Questions

- None currently blocking.

## Decisions

- **D1 Public API compatibility first**: this task will not introduce public `/documents` API names. It will add generic internal metadata contracts, query narrowing, and debug output while keeping the existing `/manuals` surface compatible.
- **D2 `/documents` is a follow-up migration**: expose a generic document-management API only after the internal `DocumentMetadata` / narrowing contract survives real usage with product manuals.

## Research References

- Archived task: `.trellis/tasks/archive/2026-05/05-17-pdf-manual-real-eval/`
- Current metadata code: `src/tagmemorag/manuals.py`
- Current search filtering: `src/tagmemorag/wave_searcher.py`, `src/tagmemorag/search_runtime.py`
- Current API filters: `src/tagmemorag/api.py::SearchFilters`
- Current CLI filters: `src/tagmemorag/cli.py search`
