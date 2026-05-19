# TagMemoRAG Architecture (living document)

## Document Status

```yaml
version: 2.0
supersedes: .trellis/tasks/archive/2026-05/05-17-production-rag-architecture/design.md
last_updated: 2026-05-17
owner: suixingchen
status: living
related_tasks_archive: 05-17-architecture-v2
```

This document is the single authoritative source for system architecture going forward. The archived `production-rag-architecture/design.md` is preserved as a historical reference but is no longer authoritative; consult it only when reconstructing the rationale of past decisions.

When a future revision supersedes this document, the same discipline applies: archive this version, publish the new one, and update `.trellis/spec/backend/index.md` to point at the new file.

## Reading Guide

Status markers used throughout this document:

- ✅ Implemented — currently live in the codebase, behavior described matches what runs.
- 🚧 Under v2 revision — design defined here, implementation deferred to a follow-up task; current code does not yet match.
- 📋 Blueprint — direction-level only; specific design decisions are deliberately deferred to the kickoff brainstorm of the corresponding follow-up task.

Where to find what:

- Phase 0–5 details (already implemented, with v2 revisions): section A.
- Phase 6–8 blueprints (not implemented; direction + open questions only): section B.
- Cross-cutting principles (eval, doc honesty): section C.
- Storage backends, follow-up roadmap, vendor reference, changelog: tail sections + appendices.

This is a long document. Each section can be read in isolation; status markers help skimming.

## Executive Position

TagMemoRAG today is a working retrieval foundation, not a complete production RAG platform. An honest summary:

**What is in place (Phase 0–5).** Knowledge-base isolation, FastAPI search/rebuild endpoints, JSON+NPZ persistence, atomic write, optional Qdrant vector backend, structured chunk lineage, structure-aware chunker (sentence-aware split, overlap, table semantic chunks, hierarchical parent/child), evidence-aware `/retrieve` with Agent context pack, admin inspect and feedback telemetry, visual evidence asset pipeline, and `/retrieve` carrying authorized visual asset references.

**What is explicitly missing.** Three production-blocking gaps stand between "works for demos" and "works as a stable platform":

1. **QueryPlan layer is absent.** Query intent, rewrites, filters, retrieval strategy, and per-request budget are implicit in code paths and request-scoped variables. There is no serializable plan object, no early-exit budget protocol, and no persisted record per `/retrieve` call. This blocks query understanding investments, blocks reproducible eval, and prevents per-request resource control.

2. **Reranker is not a first-class component.** Where rerank-like behavior exists, it lives inside specific retrieval paths rather than behind a vendor-neutral `Reranker` contract. There is no tier classification (online vs offline teacher vs fallback), no calibration step before fusion, and no documented vendor integration policy.

3. **Index upgrade is not safe.** Changing the embedding model, parser version, or chunker version today means a one-shot rebuild that overwrites the active KB. There is no shadow generation, no atomic swap, and no rollback boundary. Operators must trust the rebuild not to fail.

This document defines the contracts that close these three gaps, describes how each will land via follow-up tasks (see Follow-up Execution Roadmap), and updates the blueprint for Phase 6–8 with corrected, honest baselines. Implementation is deliberately not in scope here; this document is the contract that follow-up tasks will execute against.

The phrase "production-grade" is not used as a self-label anywhere in this document. Capabilities are stated explicitly; gaps are named explicitly.

## System Overview

```text
Source Document
  ─► Document Elements + Document Assets       (Parser + Asset extraction)
  ─► Structure-aware Chunks + Asset-derived Text (Chunker)
  ─► Text / Lexical / Metadata / Graph / Asset / (Visual) Index
  ─► Retrieval Executor
  ─► Reranker Tier
  ─► Evidence Builder    (text + page snapshot + crop + table)
  ─► Agent Context Builder  (token-budgeted context_pack)
  ─► API: /retrieve (primary)  /search (compat)  /answer (optional, future)  /assets/{id}
```

Every stage is governed by a per-request **Budget** (see A2) and produces structured artifacts that downstream stages can consume without re-deriving state. Stage-by-stage status:

| Stage | Status | Notes |
|---|---|---|
| Parser + element/asset extraction | ✅ | Markdown / TXT / text-PDF (with product-manual profile); domain keywords behind profile boundary (Phase 0). |
| Chunker (structure + sentence + table + hierarchical) | ✅ | Phase 2 production chunker. |
| Text / lexical / metadata / graph / asset indexes | ✅ | Phase 2.5 indexing strategy; Qdrant payload schema versioned. |
| QueryPlan + Budget layer | ✅ | T2 shipped 2026-05-18; rule-based planner + per-KB SQLite plan log + early-exit Budget. |
| Retrieval Executor | ✅ | Hybrid (vector + lexical + metadata + graph). |
| Reranker Tier | ✅ | T3 shipped 2026-05-18; SF Qwen3-Reranker-0.6B Tier-1; fallback to noop. Dormant by default (Settings.reranker.enabled=False). |
| Evidence Builder (text) | ✅ | Phase 3 text evidence with citations. |
| Evidence Builder (visual) | ✅ | Phase 4–5 page snapshots, asset references via `/assets/{id}`. |
| Agent Context Builder | ✅ | Token-budgeted `context_pack` with citations. |
| `/retrieve` endpoint | ✅ | Schema-versioned, evidence-aware. |
| `/search` endpoint | ✅ | Compatibility/debug; returns flat text results. |
| `/answer` endpoint | ✅ | T6 shipped 2026-05-19; optional non-streaming single-turn wrapper over `/retrieve`, default-off generation. |
| Visual retrieval (encoder + reranker) | ✅ | T8 shipped 2026-05-19; default-off deterministic visual candidate foundation. |
| OCR | ✅ | T7 shipped 2026-05-19; default-off missing-text PDF OCR ingestion foundation. |
| External connectors (DOCX/HTML/Notion/...) | ✅ | T9 shipped 2026-05-19; connector materialization foundation. |

## Domain Model

### Document

Source file and version. Fields: `doc_id`, `kb_name`, `source_file`, `content_type`, `checksum`, `version`, `metadata`.

### DocumentElement

Parser-normalized source structure. Fields: `element_id`, `doc_id`, `type` (heading / paragraph / list_item / table / table_row / image_ref / caption / page / code / footnote), `text`, `page_number`, `bbox`, `level`, `section_path`, `order`, `metadata`, `asset_refs`.

In current implementation `element_id` may be synthetic and computed at chunk-derivation time; durable element storage is not required by Phase 1 and remains optional.

### DocumentAsset

Physical or derived non-text artifact. Fields: `asset_id`, `doc_id`, `type` (source_file / embedded_image / page_snapshot / region_crop / table_snapshot / ocr_layer), `mime_type`, `storage_uri`, `page_number`, `bbox`, `width`, `height`, `checksum`, `caption`, `nearby_text`, `ocr_text`, `metadata`.

### Chunk

Retrieval unit produced from elements (not directly from raw files). Fields: `chunk_id`, `doc_id`, `element_ids`, `parent_chunk_id`, `text`, `header`, `path`, `level`, `source_file`, `page_start`, `page_end`, `bbox_refs`, `asset_refs`, `chunk_kind`, `metadata` (including `parser_profile`, `parser_version`, `chunker_version`).

### Evidence

User/API-facing proof package. Fields: `evidence_id`, `text`, `source`, `citation`, `page_range`, `section_path`, `assets`, `highlights`, `confidence`, `retrieval_reason`.

### AgentContextPack

LLM/Agent-facing context package assembled from retrieval hits and evidence. Fields: `context_id`, `query`, `items`, `token_budget`, `source_policy`, `citation_style`, `omitted_items`, `warnings`. Each item carries `context_item_id`, `content`, `content_type`, `source`, `citation_id`, `evidence_refs`, `score`, `why_selected`, `parent_context`, `metadata`.

### ID System (separated by lifetime)

| ID | Lifetime | Includes |
|---|---|---|
| `doc_id` | Persistent | derived from explicit metadata or normalized source identity + checksum policy |
| `chunk_id` | Persistent — see A1 | `doc_id`, `parser_version`, `chunker_version`, `section_path`, `element_range`, `page_range`, `text_fingerprint` |
| `element_id` | Persistent (may be synthetic, deterministic) | parser version + page/position + content fingerprint |
| `asset_id` | Persistent | `doc_id` + asset type + page/bbox or embedded-image fingerprint + asset-generation version |
| `vector_point_id` | Persistent — see A1 | `chunk_id` + `embedding_model_id` + `embedding_model_version` |
| `node_id` | Runtime (rebuild-local) | graph-local integer; never an external durable reference |
| `citation_id` | Request-scoped | points to persistent ids; not durable |
| `context_item_id` | Request-scoped | not durable |

Critically, `reranker_id` does **not** enter any persistent ID. Reranker is a read-side component and changing it must not invalidate stored vectors, chunks, or citations.

## A. Currently Implemented (Phase 0–5) — with v2 revisions

This section covers what runs today plus the contract-level revisions that follow-up tasks will execute.

### A1. ID System Split  🚧

**Before.** `chunk_id` is derived from `doc_id`, `parser_version`, `chunker_version`, `section_path`, `element_range`, `page_range`, and `text_fingerprint`. Vector storage is keyed by chunk identity, but the relationship between a stored vector and the embedding model that produced it is implicit — encoded only in the rebuild flow that overwrites prior data when the embedder changes.

**After.** Two layers, separated by what they identify:

```text
chunk_id        = hash(doc_id, parser_version, chunker_version,
                       section_path, element_range, page_range,
                       text_fingerprint)
                  # logical identity of "this piece of text"; embedder-agnostic

vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)
                  # identity of "this piece of text encoded by THIS embedder"
```

Properties:

- `chunk_id` is stable across embedder swap. The same passage of text in the same document, parsed and chunked the same way, has the same `chunk_id` regardless of which embedder will encode it.
- `vector_point_id` is the Qdrant point id and the file-level vector key. Swapping the embedder produces different `vector_point_id`s, so old and new vectors automatically coexist as separate records — they never collide.
- `reranker_id` deliberately appears in neither formula. Changing the reranker changes scoring at request time; it does not invalidate any persisted artifact.

**Migration.** Coexistence of old and new embedder vectors is delivered by A4 (IndexGeneration), not by mutating existing rows. While a shadow generation is being built with a new embedder, both generations exist in their own Qdrant collections (`{prefix}_{kb}_g1` and `{prefix}_{kb}_g2`), each addressed by its own `vector_point_id` namespace.

**Storage role of `vector_point_id`.** Because A4 isolates generations into separate Qdrant collections (and separate `g{N}/` directories), the underlying vector store can continue to key vectors by the rebuild-local `node_id` without ambiguity — within one collection there is exactly one embedder version, so `node_id` does not collide. `vector_point_id` therefore lives as a **payload field** alongside `chunk_id`, not as the Qdrant point id itself. Its job is to be a stable cross-generation handle: tools that compare g1 vs g2 (eval replay, debug joins) match rows by `vector_point_id` regardless of which collection they were retrieved from. Promoting it to point id was considered and rejected: A4's collection-per-generation already provides isolation, and changing the point id type triggers churn across every Qdrant call site for no additional safety.

**Implementation hint (for the follow-up task, not authoritative).** `qdrant_vector.collection_name(prefix, kb)` extends to `(prefix, kb, generation)`. `chunk_id` derivation lives where chunk lineage is computed today and changes only by removing any embedder coupling that may have crept in. `vector_point_id` is computed at the indexing step right before vectors are written and is added to the Qdrant payload allowlist; the point id remains `int(node_id)`.

### A2. QueryPlan and Request Budget  ✅

**Why.** Today, query intent, rewrites, filters, and resource limits are scattered across request-handling code paths and request-scoped variables. There is no serializable plan and no early-exit budget protocol. This blocks query understanding investments (HyDE, multi-query, intent classification), blocks reproducible eval (no replayable artifact), and prevents per-request resource control (Agent calls with different urgency get the same global budget).

**What.** A new cross-cutting layer between the API entry point and the retrieval pipeline. Every `/retrieve` call constructs a `QueryPlan`; every downstream component reads it; the plan is persisted (subject to privacy rules, see A2 § Persistence) for replay and eval.

```python
@dataclass
class Budget:
    latency_ms: int                                # total per-request budget
    rerank_tier: Literal["off", "tier1", "tier2"]  # tier-2 default OFF
    max_evidence: int
    allow_external_reranker: bool                  # ACL gate; private KB forces False

@dataclass
class RerankSpec:
    reranker_id: str         # vendor-neutral identity, e.g. "qwen3-reranker-0.6b@external-rerank"
    reranker_version: str
    instruction: str | None  # Qwen3-family supports task instruction; others ignore
    top_n: int

@dataclass
class QueryPlan:
    schema_version: int
    plan_id: str
    kb_name: str
    query_hash: str                  # raw query is NEVER stored; only its hash
    query_rewrites: list[str]        # PII-masked before persistence (see A2 § Persistence)
    intent: Literal["text_answer", "table_lookup", "troubleshooting",
                    "model_specific", "visual_reference", "out_of_scope"]
    filters: dict                    # metadata narrowing predicates
    strategy: dict                   # which indexes participate (vector/lexical/metadata/graph/asset)
    rerank: RerankSpec | None        # None means rerank is disabled by budget or ACL
    budget: Budget
    served_by_generation: int | None # set after retrieval; useful for A4 active/shadow comparison
    created_at: str                  # ISO-8601
```

**Early-exit protocol.** Every component (retrieval executor, reranker, evidence builder, context packer) reads `budget.latency_ms` and self-monitors. When a component detects its remaining budget is exhausted, it returns whatever it has so far and emits a `warnings: ["<component>_skipped_due_to_budget"]` entry on the response. **Components must never raise on budget exhaustion.** A `/retrieve` call always returns a structurally valid response; budget violations are visible in `warnings`, not in HTTP status.

**Planner backends.** The first implementation MUST be rule-based and lightweight: intent classification by keyword/regex, filters extracted from the query and KB metadata, no rewrites or trivial rewrites. Future LLM-based planner backends are pluggable behind the same `QueryPlan` contract — selection is deferred to a later task (T6 onward).

**Persistence.** Plans are persisted to a per-KB SQLite store; details under "Storage Backends" and the privacy rules below.

Privacy rules for persistence (mandatory):

1. **Raw query is never persisted.** Only `query_hash` (e.g. SHA-256) is stored. The raw string lives in the request scope only.
2. **Rewrites are persisted only after PII masking.** A masking pass runs over each rewrite before insertion; the masking function is treated as a security primitive and lives next to the SQLite adapter.
3. **`citation_ids`, `served_by_generation`, scores, intent, filters, and budget snapshot are persisted as-is.** These contain no user content.
4. **Plan retention is per-KB configurable** with a default rolling window (30 days). Off by default for KBs marked as private/sensitive — those KBs persist nothing beyond the response itself.

This persisted plan set is the spine of C9 (eval-as-driver). Without it, "every `/retrieve` call is a candidate eval sample" is a slogan, not a mechanism.

**T2 shipped (2026-05-18).** Implementation lives at `src/tagmemorag/queryplan/`:
- `plan.py` — `Budget` and `QueryPlan` frozen dataclasses; `Intent` enum with 6 reserved values, T2 emits 2 (`text_answer`, `out_of_scope`).
- `planner.py` — pure `build_plan(question, kb_name, settings, ...)` returns `QueryPlan`; deadline_at set via `time.monotonic()`.
- `intent.py` — keyword-based out-of-scope classifier with Settings override.
- `privacy.py` — `mask_rewrites(rewrites, rules)` PII hook; T2 ships passthrough.
- `budget.py` — `BudgetGuard` with `remaining_ms()` / `exhausted()`; used at retrieval/evidence/context-pack stage entries; never raises.
- `plan_log.py` — per-KB `{kb_root}/query_plans.db` with `PRAGMA user_version=1` schema; `PlanLog.insert_basic` sync; `BackgroundWriter` (singleton, bounded queue, drop-on-overflow) for async result UPDATEs; `prune_expired` admin-callable.
- `Settings.queryplan` block: `private_kbs`, `default_latency_ms=5000`, `default_max_evidence=8`, `default_rerank_tier="off"`, `out_of_scope_keywords`, `pii_mask_rules`, `background_writer_max_queue=1024`.
- `/search` and `/retrieve` responses include `plan_id`. `SearchRequest.budget: BudgetSpec | None` accepts per-request overrides. Out-of-scope queries short-circuit with empty results + `warnings: ["out_of_scope_intent"]`. Cache hits produce a fresh `plan_id`. Private KBs (`Settings.queryplan.private_kbs`) skip persistence entirely; `plan_id` is still returned.
- `SearchFeedback.plan_id` (optional) lets feedback rows reference the plan that produced them. Legacy jsonl rows without `plan_id` parse as empty string for backward compat.

### A3. Reranker as a First-Class Component  ✅

**Why.** Reranking is the single largest lever for retrieval quality among the components listed under "System Overview". It is currently buried inside specific retrieval paths rather than abstracted behind a vendor-neutral contract. This makes vendor migration painful, makes calibration impossible to enforce, and blocks any tier-classification policy.

**Contract.**

```python
@dataclass
class RerankDoc:
    chunk_id: str
    text: str             # may be truncated by the adapter; see Truncation rule

@dataclass
class RerankResult:
    scores: dict[str, float]               # chunk_id -> raw relevance_score
    truncated_chunk_ids: list[str]         # chunks the adapter had to truncate
    warnings: list[str]                    # e.g. ["budget_exceeded", "vendor_rate_limited"]

class Reranker(Protocol):
    id: str                  # stable identifier, e.g. "qwen3-reranker-0.6b@<vendor>"
    version: str
    max_seq_length: int      # decides truncation
    supports_instruction: bool

    def rerank(self, query: str, docs: list[RerankDoc],
               instruction: str | None, budget_ms: int) -> RerankResult: ...
```

**Cache key.** `(reranker_id, reranker_version, instruction_hash, normalized_query, chunk_id_set_hash)`. Misses are cheap to recompute; hits avoid an external call entirely.

**Tier classification.**

| Tier | Where it runs | Default | Purpose |
|---|---|---|---|
| Tier-1 online | inside `/retrieve` main path | **ON** | every-request rerank for retrieval quality |
| Tier-2 online | `/retrieve` main path, behind explicit `budget.rerank_tier="tier2"` | **OFF** | high-value queries / experiments only |
| Offline teacher | batch pipeline, never on request path | n/a | eval ground-truth labeling and Tier-1 distillation |
| Fallback chain | activated on Tier-1 outage or `allow_external_reranker=False` | configurable | local/alternative reranker, then noop |
| Noop | always installed last | always | total failure path; preserves response structure |

**Tier-2 LLM-as-judge.** Listed for completeness; default OFF. Reasoning: latency, cost, and positional bias make it unsuitable for the request path until specifically validated for a workload. Useful offline for distilling Tier-1.

**Calibration.** A reranker's `relevance_score` is **not assumed normalized**. Before any hybrid score fusion (text vector / lexical / metadata / graph / rerank), each score stream is passed through a calibration step. The calibration choice (z-score, min-max, sigmoid, isotonic) is a Phase 2.5 fusion experiment and is not specified here; what IS specified is that calibration MUST happen before fusion and MUST be reported in the debug payload.

**Truncation rule.** When the chosen reranker does not support per-doc chunking server-side, the adapter pre-truncates each `RerankDoc.text` to `reranker.max_seq_length − query_token_budget − instruction_token_budget`. The reserved budgets are properties of the adapter, kept in Appendix A. Truncated chunk ids appear in `RerankResult.truncated_chunk_ids` so the caller knows when long documents were sampled rather than read.

**ACL gate.** `budget.allow_external_reranker == False` (private/sensitive KBs) forces the rerank dispatch to bypass any external vendor and route only to local fallbacks. This check is enforced at the dispatcher, not inside individual adapters.

**Failure semantics.** A reranker call may fail (timeout, vendor rate limit, network). The dispatcher applies, in order: budget-aware retry once, fallback chain, noop. A failed rerank never produces an HTTP error from `/retrieve` — only `warnings` entries. This contract makes reranker failures non-incidents from the API consumer's perspective.

**Vendor reference.** Specific model ids, prices, rate limits, and integration constants live in Appendix A. They are not part of this contract.

**T3 shipped (2026-05-18).** Implementation lives at `src/tagmemorag/reranker/`:
- `base.py` — `Reranker` Protocol + `RerankDoc` / `RerankResultItem` / `RerankResult` / `RerankSpec` / `RerankerOutcome` dataclasses.
- `local_fallback.py` — `NoopReranker` end of fallback chain; preserves input order.
- `siliconflow.py` — `SFQwen3Reranker` adapter (Qwen3-Reranker-0.6B); httpx-based; pre-truncation; retry+breaker; HTTP 4xx no-retry; budget_ms→httpx timeout.
- `calibration.py` — 4 calibrators (MinMax default; ZScore; Sigmoid overflow-safe; Identity); shared edge-case handling.
- `circuit_breaker.py` — process-internal Lock-protected breaker; threshold + cooldown; success resets.
- `cache.py` — `RerankCache` LRU; key-tuple `(reranker_id, version, instruction_hash, query_hash, chunk_id_set_hash)`; generation-independent.
- `dispatcher.py` — `RerankerDispatcher` 6-step routing tree (enabled / tier / ACL / budget / cache / vendor); never raises to caller; falls back to noop on any failure.
- `Settings.reranker` block: `enabled` (default False, ops flips in yaml), `default_tier`, `provider`, `model_id`, `model_version`, `instruction`, `top_n=20`, `rerank_candidates_n=100`, `calibrator="minmax"`, `max_seq_length=32768`, `query_token_budget=256`, `instruction_token_budget=64`, `retry_max=1`, `retry_backoff_ms=200`, `circuit_breaker_threshold=3`, `circuit_breaker_cooldown_seconds=30`, `min_budget_ms=500`, `hard_timeout_ms=3000`, `downstream_reserve_ms=200`, `cache_enabled=True`, `cache_max_entries=5000`, `api_key_env`, `base_url`.
- `/retrieve` integration: when reranker active, `execute_search` top_k expanded to `rerank_candidates_n`; dispatcher reorders; `build_retrieve_response` truncates to user's `token_budget`. `/search` (legacy) unchanged.
- T2 plan log `rerank_json` column populated with `vendor_used / calibrator / latency_ms / cache_status / top_n_returned / truncated_count / warnings`.
- Feature flag `Settings.reranker.enabled=False` keeps T3 dormant on production until ops flips it. Cleanly reverts to T2 behavior.

### A4. IndexGeneration  🚧

**Why.** Today, changing the embedding model, parser version, or chunker version is a one-shot rebuild that overwrites the active KB. There is no shadow, no atomic swap, and no rollback boundary. Operators must trust the rebuild not to fail mid-flight, and a successful-but-regressing rebuild has no safe undo path. This is the single largest operational risk in the platform today.

**Mechanism.** Generations: each KB carries a numbered sequence of immutable index sets. At any moment a KB has at most one active generation and at most one shadow generation under construction.

```text
   [empty]
      │ build initial
      ▼
   [g1 active]
      │ build shadow (new embedder/chunker/parser version)
      ▼
   [g1 active, g2 shadow]
      │ swap                  │ rollback (before retire)
      ▼                       ▲
   [g1 retired*, g2 active]  ─┘
      │ retire
      ▼
   [g2 active]

   * "retired" = pointer flipped, files still on disk until explicit retire admin call.
```

**Storage layout.**

```text
{kb_root}/
  index.json              # active_generation, shadow_generation, history[]
  g1/
    graph.json
    chunk_identity.json
    vectors.npz                  # if NPZ backend
    qdrant_pointer.json          # if Qdrant backend (collection name)
    assets/                      # asset references for this generation
  g2/
    ...                          # same shape; built in shadow, swapped in atomically
```

`index.json` is updated via the file-level atomic write primitive that already exists (`storage/atomic.atomic_write`). The pointer flip is a single `os.replace` on `index.json`; it does not need cross-file coordination.

**T1 scope (initial implementation).** The first IndexGeneration follow-up task (T1) intentionally limited per-generation isolation to KB-level core artifacts: `graph.json`, `vectors.npz` (or the `{prefix}_{kb}_g{N}` Qdrant collection), `chunk_identity.json`, `anchors.json`, and the GraphState `meta.json`. KB-shared global artifacts — EPA basis, tag co-occurrence, tag intrinsic residuals, and tag embeddings — lived under `{data_dir}/_global/...` and were not generation-isolated by T1.

**T1.5 shipped 2026-05-19.** Derivative builders now support generation-aware path overrides via `KbPaths`. Legacy full/incremental rebuild callers still use `_global` by default, while generation-oriented callers can route EPA basis, tag co-occurrence, and intrinsic-residual inputs through `paths.generation_root`. This keeps existing deployments compatible and gives shadow/generation flows an explicit path to colocate derivatives with core generation artifacts. Tag embeddings remain stored in the registry as canonical tag vectors; generation-local copies are still a future optimization if replay/shadow evaluation needs immutable tag-vector snapshots.

**Qdrant collection naming.** `{prefix}_{kb}_g{N}`, extending the current `{prefix}_{kb}` convention. Existing collections are treated as `g1`-equivalent during initial migration: a one-time rename or alias accomplishes the upgrade without rebuild.

**Trigger conditions for a new generation.** Any of these version fields changing must trigger a shadow build, never an in-place mutation:

- `parser_version`
- `chunker_version`
- `embedding_model_id` or `embedding_model_version`
- `index_schema_version` (Qdrant payload schema)

In contrast, content-only changes (a new document added to the KB) update the active generation in-place via existing incremental rebuild paths. Generations are about engine versions, not data growth.

**Admin API shape (REST).**

| Endpoint | Action | Reversible? |
|---|---|---|
| `POST /admin/generation/build-shadow` | starts background rebuild into `g{N+1}` with new versions | yes (cancel before swap) |
| `POST /admin/generation/swap` | atomic pointer swap in `index.json` | yes (swap back) until retire |
| `POST /admin/generation/retire` | deletes retired generation files and Qdrant collection | **no** |
| `GET  /admin/generation/status` | returns active id, shadow id, build progress, last-swap time | n/a |

**Rollback boundary.** Swap is reversible by swapping pointers back, as long as the old generation has not been retired. Once retire is called, the previous generation is gone. Operators must wait through a configurable observation window (default suggestion: 24 hours; finalized in T1) before retire.

**No traffic split, by design.** This document deliberately does not implement gradual traffic splitting (10% → 50% → 100%). At current single-tenant scale the value is low and the control-plane complexity is high. The same goal — comparing a new generation against the active one on real traffic — is achieved more cheaply by replaying persisted QueryPlans (see C9) against the shadow generation offline. When scale demands it, traffic split can be added on top of this design without rework.

**Eval gate before swap.** Swap MUST be preceded by an eval gate run defined per follow-up task: replay the rolling QueryPlan window against shadow, compare metrics, swap only on green. The exact eval slice composition is owned by C9 and the follow-up task that lands eval-as-driver tooling.

### A5. WAVE Repositioning  🚧

**Status.** Experimental — default off.

**Why repositioned.** The archived `production-rag-architecture/design.md` listed WAVE under "Strengths Worth Preserving" as a differentiated topology/rerank layer. As of 2026-05-17 this is no longer accurate: the three WAVE readiness flags (Phase 3, Phase 3.5, Phase 4) were empirically evaluated and all set to KEEP_OFF. WAVE is not on the critical retrieval path; it does not contribute to current `/retrieve` quality.

This document does not delete or deprecate WAVE code. It re-labels the feature.

**What this means concretely.**

- WAVE code remains in the repository and remains buildable.
- All three WAVE readiness flags default OFF and are documented as default OFF in operator-facing documentation.
- WAVE does not appear in the system overview as a critical component.
- Eval results that exercise WAVE are clearly labeled as research/exploration, not production baselines.

**Promotion criteria — when WAVE may move back to a non-experimental status.**

1. A defined production-eval slice (concrete fixtures, not ad-hoc queries) shows reproducible, statistically meaningful improvement with WAVE enabled.
2. The improvement holds across at least two parser/chunker generation upgrades — i.e. it is not coupled to a particular generation's quirks.
3. Performance budget impact (latency p50/p99, memory, rebuild time) is within the same envelope as the baseline.
4. A follow-up task explicitly proposes the promotion, with the eval evidence attached.

**Cross-references.** Memory: `wave-readiness-flags-empirical-keep-off`. The empirical evaluation that produced the KEEP_OFF decisions is documented in archive task `05-17-wave-readiness-flags`.

## B. Blueprints (Phase 6–8) — direction + open questions only

This section is direction-level, not contract-level. Each phase below is **not yet implemented** and the design decisions inside each phase are deliberately deferred to the kickoff brainstorm of the corresponding follow-up task. The reason: predictions made too early grow stale before they are executed. What is fixed here is direction and the questions that must be answered before implementation starts.

### B6. Phase 6 — `/answer` endpoint  ✅ T6 Kickoff Shipped

**Shipped 2026-05-19.** T6 adds an optional non-streaming, single-turn `/answer` endpoint that internally reuses `/retrieve`, then passes the resulting `context_pack` to a configured generation provider. `/retrieve` remains the primary external contract and is independently usable; `/answer` is a convenience for clients that prefer a managed answer endpoint over composing their own LLM call.

The endpoint reuses `/retrieve`'s evidence and citation policy. It degrades in-band: insufficient retrieval returns `answer.kind="refusal"`, disabled generation returns `answer.kind="error"` with `refusal_reason="generation_disabled"`, and provider failure returns `answer.kind="error"` with `refusal_reason="generation_failed"`. All paths use HTTP 200 and preserve the retrieval payload by default so callers still have actionable output.

**Contract.**

- Request: `AnswerRequest` extends `RetrieveRequest` with `answer_token_budget` and `include_retrieve`.
- Response: `schema_version="answer.v1"`, stable `trace_id`/`plan_id`, top-level `warnings`, and an `answer` object with `kind`, `text`, `confidence`, `citations`, `refusal_reason`, `missing_evidence_hints`, `model_id`, `model_version`, `prompt_version`, and answer-local `warnings`.
- Generation is disabled by default via `Settings.answer.enabled=False`.
- Providers implement the vendor-neutral `AnswerGenerator` protocol. T6 ships a deterministic noop provider and an OpenAI-compatible chat-completions HTTP provider.
- Prompt-injection defense is role separation plus structured, quoted retrieval context. Retrieved manual text is always untrusted source data and may not override system instructions.
- Citation validation drops generated citations that are not present in the retrieved citation set and adds `answer_dropped_invalid_citations`.

**Eval stance.** T6 uses deterministic unit/API contract tests and citation coverage checks. It deliberately does not use LLM-as-judge for regression gating.

**Deferred.** Streaming, multi-turn state, generation cache, tool-calling, prompt/model rollout policy, and faithfulness metrics beyond deterministic citation checks remain follow-up work.

### B7. Phase 7 — Visual Track  📋 Blueprint

Phase 7 in the archive design bundled OCR and visual embedding into one large milestone. This document splits it into two independent tracks because their cost, complexity, and value profiles are different.

#### B7A. OCR pipeline  ✅ T7 Kickoff Shipped

**Shipped 2026-05-19.** T7 adds a default-off OCR text ingestion foundation for PDF pages where native `pypdf` extraction yields no useful text. OCR text feeds into the existing parser/chunker, text/lexical indexes, `/retrieve`, and `/answer`; OCR is not a parallel retrieval path. Page snapshots remain the visual evidence asset model and are not duplicated by OCR.

OCR is the cheaper, higher-coverage half of visual document understanding. It alone unlocks a large share of "the answer is on page X but the page is a scan" cases.

**Contract.**

- `Settings.ocr.enabled` defaults to `False`.
- `OCRProvider` is vendor-neutral. T7 ships only a deterministic fixture provider; production OCR providers are follow-up work.
- Trigger policy is `missing_text`: OCR runs only for PDF pages where native extraction produces no useful lines.
- OCR output is page-block text in the MVP. Layout-aware table/region reconstruction is deferred.
- OCR chunks are normal chunks with `parser_profile="pdf_ocr:<profile>"`, page metadata, and `ocr_provider` / `ocr_version` / `ocr_trigger` / `ocr_source` lineage.
- OCR provider/version/trigger/source participate in chunk identity, so OCR changes can force new chunk ids and embeddings.
- OCR failures degrade by default and are summarized with bounded low-cardinality failure reasons. Strict mode can fail rebuild.
- Rebuild metadata may include `meta["ocr"]` with enabled/provider/version/trigger counts, never raw OCR text.

**Deferred.** Production OCR backend selection, image-file OCR, layout-aware tables/regions/bounding boxes, `ocr_layer` asset persistence, async OCR workers, LLM correction, and all visual embedding/reranking work remain follow-up tasks.

#### B7B. Visual retrieval  ✅ T8 Kickoff Shipped

**Shipped 2026-05-19.** T8 adds a default-off visual retrieval foundation for queries where the user's intent is visually grounded ("show the diagram", "where is the button", "find the part labeled X"). The MVP is deterministic and manifest-backed; it proves candidate generation, rerank boundary, fusion, and safe response shape without adding production visual model dependencies.

Crucially, the visual path remains a **two-component** path:

- A visual **encoder** indexes pages or page regions into a visual vector space at index time.
- A visual **reranker** scores `(query, candidate_visual)` pairs at query time.

These are different responsibilities. The archive design conflated them. A managed visual reranker (e.g. an external multimodal API) does not remove the need for an encoder on the indexing side; without an encoder there is nothing to rerank.

**Contract.**

- `Settings.visual_retrieval.enabled` defaults to `False`.
- `VisualCandidateProvider` produces candidates over existing `DocumentAsset`s. The T8 provider is deterministic and scores manifest text fields (`caption`, `nearby_text`, `ocr_text`, source file, and safe metadata) by token overlap.
- `VisualReranker` receives candidate assets and may adjust order/scores, but cannot invent assets. T8 ships a noop reranker.
- Visual candidates are considered only when visual intent is detected by default.
- Fusion appends visual-only evidence after text evidence, deduping assets already attached to text evidence. This preserves text result order and avoids destabilizing existing retrieval quality.
- Public payloads use existing asset descriptors and must not expose storage keys, checksums, vectors, local paths, raw bytes, or secrets.
- `visual_evidence.retrieval` contains bounded counts/reasons for diagnostics.

**Deferred.** Production visual encoder selection, production visual reranker selection, vector/late-interaction storage, training or finetuning, automatic region detection/cropping, UI image galleries, and visual answer generation remain follow-up work.

### B8. Phase 8 — External Connectors  ✅ T9 Kickoff Shipped

**Shipped 2026-05-19.** T9 adds the connector materialization foundation for non-file or generated sources. Connectors normalize records into supported local document files plus `.metadata.json` sidecars, then reuse the existing parser/chunker/indexer/retrieval pipeline. The chunker boundary is preserved — connectors are additional source adapters, not parallel retrieval pipelines.

**Contract.**

- `Settings.connectors.enabled` defaults to `False`.
- `ConnectorProvider.sync(kb_name)` returns a bounded snapshot of `ConnectorRecord`s.
- T9 ships a fixture provider only; production connectors are follow-up tasks.
- Materialization writes supported documents (`.md`, `.txt`, `.pdf`) and metadata sidecars under `{connectors.materialized_root_dir}/{kb_name}`.
- Existing `build_kb()` remains authoritative after materialization.
- Soft deletes materialize tombstone sidecars with `status="deleted"`; physical deletion is deferred.
- Sync summaries are low-cardinality counts/reasons and must not include raw document text, secrets, remote credential material, or absolute local paths.

**Deferred.** Real SaaS connectors, authentication and credential rotation, webhooks, ACL enforcement, connector-specific rate limiting, binary conversion beyond supported suffixes, and connector management UI remain follow-up work.

## C. Cross-cutting Principles

These two principles apply across every section of this document and across every follow-up task that this document spawns.

### C9. Eval-as-driver  ✅

**Principle.** New retrieval-affecting work begins by exercising eval, not by writing implementation. This is a mechanism, not a slogan; the mechanism is grounded in the QueryPlan persistence introduced in A2.

**Mechanism.**

1. Every `/retrieve` call produces a `QueryPlan`. Plans are persisted to per-KB SQLite (privacy-masked per A2 § Persistence).
2. A replay tool, given a generation id and an optional plan filter, re-executes the persisted plan set against the chosen generation and produces metric deltas vs the baseline (active generation).
3. New phase tasks must list, in their own PRD, which eval slices (subsets of the persisted plan set, plus any synthetic fixtures) they will exercise. The task is not eligible for `task.py start` until the eval-slice list is filled in.
4. A4 generation swap is gated on this same replay: a shadow generation is not swapped to active until the replay shows the agreed metric criteria are met.

**Replay tool contract.**

```text
trellis-rag-eval replay \
  --kb <kb_name> \
  --generation g2 \
  [--baseline g1] \
  [--filter intent=table_lookup,created_after=2026-05-01] \
  [--metrics hit@5,citation_correctness,latency_p50] \
  [--output-format json|markdown]
```

The tool reads QueryPlans from SQLite, replays each against the chosen generation, computes metrics, and prints the deltas vs baseline.

**T5 shipped 2026-05-19.** `scripts/trellis_rag_eval.py replay` implements the offline MVP: local generation replay from persisted QueryPlans, optional baseline deltas, JSON/Markdown output, plan filters, and historical rerank summary from `rerank_json`. It does not call external reranker vendors during replay and does not evaluate generated `/answer` output.

#### T5 Replay CLI Implementation Contract

**1. Scope / Trigger.** Applies when adding or changing offline replay of persisted QueryPlans, generation-swap gates, replay metrics, or rerank impact reporting.

**2. Signatures.**

- Command: `python scripts/trellis_rag_eval.py replay --kb <kb_name> --generation <active|shadow|gN|N> [--baseline <active|shadow|gN|N>] [--config <path>] [--filter key=value ...] [--metrics a,b,c] [--limit N] [--output-format json|markdown]`
- Package entry: `tagmemorag.replay.cli:main(argv: list[str] | None = None) -> int`
- Loader: `ReplayPlanLoader(kb_name, settings).load(filters=ReplayFilters(), limit=N) -> (list[ReplayPlan], list[SkippedReplayRow])`
- Generation loader: `load_generation_state(kb_name, settings, generation) -> GraphState`

**3. Contracts.**

- Input store is `{settings.storage.data_dir}/{kb_name}/query_plans.db`, schema version `<= PLAN_LOG_SCHEMA_VERSION`; replay must not create or migrate the DB.
- Replay query comes from `query_rewrites_masked_json[0]`; raw query text is not separately persisted.
- Supported filters are `intent`, `created_after`, `created_before`, `cache_status`, and `rerank_vendor`; date filters normalize to UTC `YYYY-MM-DDTHH:MM:SSZ`.
- Generation selectors support `active`, `shadow`, `gN`, and `N`; `shadow` is replayable only when the shadow slot is ready.
- Replay uses local NPZ generation artifacts via `KbPaths(kb_name, settings, generation=N)` and a temporary `GraphState`; it must not mutate `AppState`, swap generations, or write plan-log rows.
- Replay must not call external reranker vendors by default. Rerank impact is summarized from persisted `rerank_json`.
- JSON report schema version is `replay_report.v1`; Markdown output is operator-facing and must not print raw query text by default.

**4. Validation & Error Matrix.**

- Missing `query_plans.db` -> CLI exit `2` with `{ "error": ... }` in JSON mode.
- Future plan-log schema version -> exit `2`.
- Unknown filter key, invalid date, duplicate filter, or non-positive limit -> exit `2`.
- Missing `index.json`, unknown generation, retired generation, not-ready shadow, or missing generation artifacts -> exit `2`.
- Qdrant-only replay without local NPZ artifacts -> exit `2` until a separate online-Qdrant replay contract exists.
- Malformed individual plan rows -> skip row, include `skipped_rows`, continue replay.
- Per-case replay exception -> record case `error`, exclude it from successful metric denominators, continue replay.
- Baseline replay with `any_hit_rate_delta < 0` -> exit `3`; other MVP deltas are informational.

**5. Good/Base/Bad Cases.**

- Good: replay `g2` against `g1`, filters select real plan rows, target/baseline metrics and deltas are emitted, and rerank fallback/cache summary is derived from `rerank_json`.
- Base: target-only replay emits metrics and cases with no baseline or deltas.
- Bad: replay calls the live reranker dispatcher or external HTTP provider without an explicit future opt-in mode; replay writes new rows into `query_plans.db`; Markdown output includes full query text.

**6. Tests Required.**

- Filter parser: valid filters, invalid keys, duplicate filters, cache status validation, date normalization.
- Loader: happy path, missing DB, future schema, malformed JSON rows, blank query, SQL filters, rerank vendor filter, limit.
- Generation: selector resolution, active/shadow semantics, retired/missing artifacts, Qdrant-only rejection.
- Runner/metrics: local retrieval stack replay, per-case errors, no reranker dispatcher call path, aggregate metrics, deltas, rerank summary.
- CLI: JSON output, Markdown output, missing artifact exit `2`, baseline regression exit `3`.
- Compatibility: legacy `scripts/replay_against_generation.py` tests remain green until that T1 script is intentionally retired.

**7. Wrong vs Correct.**

Wrong:

```python
from tagmemorag.api import app_state

state = app_state.get_current(kb_name)
rerank_outcome = _rerank_dispatcher().rerank(plan, results, guard)
```

This replays whichever generation is active in process memory and may call the external reranker path.

Correct:

```python
state = load_generation_state(kb_name, settings, generation)
cases = replay_plans(plans=plans, state=state, settings=settings, generation=generation)
rerank_summary = summarize_rerank(plans)
```

This targets the requested generation artifacts, keeps replay offline, and derives reranker impact from persisted metadata.

**Eval data lifecycle.** Plans are kept in a rolling window — default 30 days, configurable per KB. Plans older than the window are pruned. Plans from KBs marked private/sensitive are never persisted (A2 rule 4). Manually curated fixtures (added by a human reviewing failures via Phase 3.5 admin inspect) are kept indefinitely until explicitly retired; they are stored separately from the rolling window.

**Why this matters.** Without a mechanism, "eval-driven" stays a slogan. With this mechanism, every change that touches retrieval, indexing, ranking, or evidence has a concrete, replayable test set drawn from real traffic — and a new phase cannot start without committing to which slice it will test.

### C10. Documentation Honesty  ✅ (this document is the first instance)

**Principle.** This document — and any document that supersedes it — must be honest about what is implemented, what is not, and what is experimental. Three rules enforce this.

**Rule 1. No "production-grade" self-label.** The phrase "production-grade", as a self-applied claim about the system, is forbidden in this document. Capabilities are stated explicitly (what runs, what response shape exists, what eval gates are in place). Gaps are named explicitly. The reader decides whether the result is "production-grade" for their context.

A grep test enforces this rule: the validator script described in this task's `implement.md` fails the document if `production-grade` appears outside Appendix B (Changelog) where it is referenced as the language being retired.

**Rule 2. Vendor specifics live only in Appendix A.** Vendor names, model ids, prices, rate limits, and integration constants change without code changes. Putting them inside contracts means contracts churn for non-architectural reasons. They are confined to Appendix A, which carries an "as of" date and is updated by the integration task that uses them.

**Rule 3. Experimental features are labeled, not buried.** Any feature that is default-off and unproven is marked Experimental in its section heading and is excluded from the system overview. WAVE (A5) is the canonical example. Promotion criteria are explicit; promotion happens by follow-up task with attached evidence.

**Why this matters.** A document that overstates its system blocks honest follow-up work. New contributors and AI agents read documents literally; "production-grade" gets quoted back at the team. By writing the document the way the system actually behaves today, we keep the next decision (what to build next, what to fix first) anchored in reality.

## Known Architectural Gaps

Following the C10 rule that gaps are named explicitly, the following are intentional, currently-accepted gaps. They are not bugs to be filed; they are decisions to defer. Each entry states what is missing, why deferral is acceptable today, and what would force the gap to be closed.

### G1. Document-level ACL  📋

**What is missing.** Authorization is enforced at the KB level: a caller either can read a KB or cannot. There is no per-document permission model. A `doc_acl` shape — `{tenant_id, owner, group_ids[], visibility}` — is not present in the domain model, not in Qdrant payload filters, not in graph node filters, and not in the asset serving authorization path.

**Why deferral is acceptable today.** Current deployment is single-tenant. Every reader of a KB is authorized to read all documents in that KB. KB-level isolation is a sufficient permission boundary for this scope.

**What would force closing the gap.** Any of:

1. Multi-tenancy within a single KB (different teams sharing one KB but with restricted views).
2. A connector (B8) whose remote system carries per-document ACLs that must be honored locally — the connector ACL adapter referenced in B8 then needs a local target shape to map onto, and that target is `doc_acl`.
3. Compliance requirements that mandate per-document audit and access control (e.g. legal hold, regulated content).

**Where it would land.** Domain model `Document` gains an `acl` field. Qdrant payload schema (governed by `index_schema_version` per A4) gains ACL fields, triggering a new generation. Graph node iteration in retrieval gains an ACL filter step. Asset serving (`/assets/{id}`) consults the same ACL.

This entry exists so that the next reader knows the gap is known, the trigger conditions are defined, and the integration shape is sketched — even though no follow-up task is created today.

## Storage Backends

The storage layer is split by data shape, each backed by a small adapter under `src/tagmemorag/storage/`. Adding a backend means adding a new adapter, not modifying retrieval/indexing code.

| Backend | Module | Role | Status |
|---|---|---|---|
| JSON graph | `storage/json_graph.py` | graph topology + node/edge metadata | ✅ |
| JSON anchor | `storage/json_anchor.py` | anchor system | ✅ |
| NPZ vector | `storage/npz_vector.py` | vectors (default file backend) | ✅ |
| Qdrant vector | `storage/qdrant_vector.py` | vectors (optional, generation-aware naming per A4) | ✅ |
| Local/S3 blob | `storage/...` (existing manual blob store) | source files + assets | ✅ |
| **SQLite plan log** | `queryplan/plan_log.py` | QueryPlan persistence per A2/D6 | ✅ T2 shipped 2026-05-18 |
| Atomic write primitive | `storage/atomic.py` | safe single-file replace | ✅ |

**SQLite plan log design notes.**

- File path: `{kb_root}/query_plans.db` — one file per KB, no cross-KB schema.
- No ORM. Standard library `sqlite3` only. Schema is small and bounded.
- Schema versioning via `PRAGMA user_version`. Migrations are forward-only; the migration runs on first open of a DB whose `user_version` is older than the current code's expected version.
- Connection model: single connection per KB, opened lazily, with `WAL` journal mode. Concurrent reads OK; writes are serialized. The `/retrieve` write path inserts one row per call; latency budget for the insert is ≤2 ms — beyond that the insert is dropped with a metrics counter increment, not held against the request.
- Privacy: enforced by the adapter, not by callers. The adapter never accepts a raw query string for storage; it accepts a hash. Rewrites are masked inside the adapter via a configurable mask function before insertion.
- Backup is the operator's responsibility — file copy while the WAL is checkpointed is sufficient.

**Why SQLite, not PostgreSQL.** Current scope is single-tenant and single-machine. SQLite ships with Python; PostgreSQL adds a process dependency, ORM, connection pool, migration tool, and backup operations to the deployment surface. SQLite's schema and indexes are real (unlike JSON Lines), and the schema migrates cleanly to PostgreSQL later if multi-machine scale demands it.

## Follow-up Execution Roadmap

The following tasks are the work this document creates. They are NOT pre-created via `task.py create`; each is created when its prerequisites are met and its kickoff brainstorm begins. The roadmap exists so dependency order does not need to be re-derived.

| ID | Title | Depends on | Priority | Scope hint |
|---|---|---|---|---|
| T1 | IndexGeneration mechanism + ID system split | — | P1 | A1 + A4 combined; touches `qdrant_vector`, `state.AppState`, file layout, admin API, atomic index.json swap |
| T2 | QueryPlan + Budget contract + SQLite plan log | T1 | P1 | A2 + D6 combined; introduces planner protocol, early-exit protocol, persistence adapter |
| T3 | Reranker first-class component + initial vendor integration | T2 | P1 | A3; defines Reranker Protocol, dispatcher, calibration step, fallback chain; first vendor concrete in Appendix A |
| T4 | WAVE repositioning + documentation honesty patch | — | P3 | A5 + C10; small task; updates operator-facing docs and code-level doc strings to match this architecture |
| T1.5 | IndexGeneration derivatives isolation | T1 | P3 | ✅ Shipped 2026-05-19; generation-aware derivative path overrides with legacy `_global` compatibility |
| T5 | eval-as-driver replay tool | T2 | P2 | ✅ Shipped 2026-05-19; CLI tool, metric set, plan-filter language |
| T6 | Phase 6 `/answer` kickoff | T2, T3 | P2 | B6 (independent brainstorm; this task only enters after T2+T3 land) |
| T7 | Phase 7A OCR kickoff | T1 | P2 | B7A (independent brainstorm) |
| T8 | Phase 7B visual retrieval kickoff | T1, T7 | P3 | B7B (independent brainstorm) |
| T9 | Phase 8 connectors kickoff | T1 | P3 | B8 (independent brainstorm; connector-by-connector tasks beneath this one) |

Priority key: P1 = must precede further surface-area expansion; P2 = high-value next steps; P3 = scoped to maturation, not blocking.

T1, T2, T3 form a strict chain: T1 unlocks safe rebuilds; T2 unlocks request-level control and eval persistence; T3 turns ranking quality into a vendor-pluggable component. After T1+T2+T3 the platform is ready for `/answer` (T6) and for the visual track (T7+T8).

T4 is independent — it is documentation discipline catching up to reality and can land at any time.

T5 shipped the eval-as-driver MVP. It remains P2 in the roadmap history because the persisted plan set takes time to fill the rolling window after T2 ships; running replay too early can still produce thin eval slices.

T7 OCR is broadly useful and is the cheaper half of Phase 7; it can ship before T8 visual retrieval and is the recommended path.

## Appendix A — Reference Implementations (as of 2026-05-17)

Vendor- and model-specific values that this document refers to. These details may change without architectural impact; only this appendix needs an update.

### A.1 Reranker — primary online tier

- Model: `Qwen/Qwen3-Reranker-0.6B`
- Endpoint: `POST https://api.siliconflow.cn/v1/rerank`
- Auth: `Authorization: Bearer $SILICONFLOW_API_KEY`
- Context length: 32K tokens
- Pricing: ¥0.07 / M input tokens (input only)
- Rate limit (L0 tier): RPM 2,000 / TPM 1,000,000
- Supported request fields beyond standard: `instruction` (Qwen3-family exclusive)
- Unsupported fields the caller must work around: `max_chunks_per_doc`, `overlap_tokens` — the caller pre-truncates documents
- Response: `{id, results: [{index, document?, relevance_score}], meta: {tokens, billed_units}}`. `relevance_score` is **not** guaranteed normalized; calibration is required before fusion (A3).
- Reserved budgets used by the adapter:
  - `query_token_budget`: 256 tokens (sufficient for typical queries + slack)
  - `instruction_token_budget`: 64 tokens
  - per-doc cap: `32_768 - 256 - 64 = 32_448` tokens
- Source: SiliconFlow rerank API documentation, retrieved 2026-05-17.

### A.2 Reranker — offline teacher

- Model: `Qwen/Qwen3-Reranker-8B`
- Endpoint: same as A.1
- Use: batch labeling for eval ground truth; teacher signal for distilling Tier-1
- Never on the request path

### A.3 Reranker — fallback chain entries

In dispatcher order after Tier-1 outage or `allow_external_reranker=False`:

- `Pro/BAAI/bge-reranker-v2-m3` — supports `max_chunks_per_doc` and `overlap_tokens`; useful when chunks are long; vendor-side chunking offloads adapter complexity
- Local cross-encoder (placeholder; selection deferred): a future distilled local model, populated when the offline teacher pipeline produces one
- Noop reranker — last in chain; preserves response structure on total failure

### A.4 Visual reranker option for B7B

- Model: `Qwen/Qwen3-VL-Reranker-8B`
- Context: 32K
- Use: candidate option for the visual rerank tier in B7B; selection is deferred to T8
- Note: this is a reranker only; B7B still requires a separate visual encoder for indexing

### A.5 Embedding model — current

- Whatever is configured in `Settings.embedding_model_id` and `Settings.embedding_model_version` at deployment time. These two fields are the authoritative source; this appendix does not duplicate them. Generation upgrades (A4) are triggered when either field changes.

## Appendix B — Changelog vs archive design

Comparison against the archived `production-rag-architecture/design.md`. This is the high-level diff; for full historical context, consult the archived document directly.

| Topic | Archive design | architecture.md v2 |
|---|---|---|
| WAVE | Listed under "Strengths Worth Preserving" | A5: Experimental, default off; promotion criteria explicit |
| `chunk_id` derivation | Single-layer; embedder coupling implicit in rebuild flow | A1: two-layer (`chunk_id` and `vector_point_id`); embedder swap no longer mutates rows |
| Reranker | Mentioned across Phase 2.5 / Phase 3 prose | A3: first-class component with Protocol, tier table, calibration requirement, ACL gate |
| Index upgrade | One-shot rebuild overwrites active KB | A4: named generations with shadow build, atomic swap, retire boundary |
| QueryPlan | Implicit in handler code | A2: cross-cutting layer; serializable; persisted (privacy-masked) |
| Phase 7 | OCR + visual embedding bundled into one milestone | B7 split into B7A (OCR) and B7B (visual retrieval); encoder vs reranker separation called out |
| Vendor specifics (model ids, prices, rate limits) | Mixed into design body where mentioned | Appendix A only |
| `/answer` streaming | Implied as a future detail | B6: explicit open question, deferred to task kickoff |
| Connector ACL | Treated as one abstract surface | B8: connector-specific adapters; no single abstraction |
| Document-level ACL | Implicit / mixed with KB-level isolation | G1: named explicit gap with defined trigger conditions for closing |
| `production-grade` self-label | Used in body | C10: forbidden in body; replaced by explicit gap naming |
| Eval | Listed as a Phase 3.5 capability | C9: cross-cutting principle backed by persisted QueryPlans + replay tool (T5) |
| Storage backends | Mentioned per-component | Storage Backends section consolidates all adapters; SQLite added for QueryPlan |
| Follow-up roadmap | Embedded in Phase descriptions | Dedicated Follow-up Execution Roadmap with explicit dependencies |

The archive document is preserved unchanged. When historical reasoning is needed (why a specific decision was made before this revision), consult the archived file. For decisions going forward, this document is authoritative.
