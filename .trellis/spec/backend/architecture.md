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
| QueryPlan + Budget layer | 🚧 | New cross-cutting layer (A2). |
| Retrieval Executor | ✅ | Hybrid (vector + lexical + metadata + graph). |
| Reranker Tier | 🚧 | New first-class component (A3). |
| Evidence Builder (text) | ✅ | Phase 3 text evidence with citations. |
| Evidence Builder (visual) | ✅ | Phase 4–5 page snapshots, asset references via `/assets/{id}`. |
| Agent Context Builder | ✅ | Token-budgeted `context_pack` with citations. |
| `/retrieve` endpoint | ✅ | Schema-versioned, evidence-aware. |
| `/search` endpoint | ✅ | Compatibility/debug; returns flat text results. |
| `/answer` endpoint | 📋 | Phase 6 blueprint (B6). |
| Visual retrieval (encoder + reranker) | 📋 | Phase 7B blueprint (B7B). |
| OCR | 📋 | Phase 7A blueprint (B7A). |
| External connectors (DOCX/HTML/Notion/...) | 📋 | Phase 8 blueprint (B8). |

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

**Implementation hint (for the follow-up task, not authoritative).** `qdrant_vector.collection_name(prefix, kb)` extends to `(prefix, kb, generation)`. `chunk_id` derivation lives where chunk lineage is computed today and changes only by removing any embedder coupling that may have crept in. `vector_point_id` is computed at the indexing step right before vectors are written.

### A2. QueryPlan and Request Budget  🚧

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

### A3. Reranker as a First-Class Component  🚧

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
  meta.json              # active_generation, shadow_generation, history[]
  g1/
    graph.json
    chunk_identity.json
    vectors.npz                  # if NPZ backend
    qdrant_pointer.json          # if Qdrant backend (collection name)
    assets/                      # asset references for this generation
  g2/
    ...                          # same shape; built in shadow, swapped in atomically
```

`meta.json` is updated via the file-level atomic write primitive that already exists (`storage/atomic.atomic_write`). The pointer flip is a single `os.replace` on `meta.json`; it does not need cross-file coordination.

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
| `POST /admin/generation/swap` | atomic pointer swap in `meta.json` | yes (swap back) until retire |
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

### B6. Phase 6 — `/answer` endpoint  📋 Blueprint

**Direction.** Add an optional `/answer` endpoint that internally calls `/retrieve`, then passes the resulting `context_pack` to a configured LLM, returning a generated answer with citations. `/retrieve` remains the primary external contract and is independently usable; `/answer` is a convenience for clients that prefer a managed answer endpoint over composing their own LLM call.

The endpoint must reuse `/retrieve`'s evidence and citation policy. It must degrade — when generation fails, it returns the retrieval context so the caller still has actionable output. Streaming is added at this phase, both for `/answer` token output and (opportunistically) for `/retrieve` evidence.

**Why now.** Phase 0–5 stabilized the retrieval/evidence contract. With QueryPlan (A2), Reranker (A3), and IndexGeneration (A4) defined, the retrieval foundation is stable enough that a generation layer on top will not destabilize it.

**Open questions to resolve at task start (≥6).**

1. **Refusal contract.** What is the wire-level shape of "insufficient evidence to answer"? Fields needed: `confidence`, `reason`, `partial_answer`, `missing_evidence_hints`. Is refusal a distinct response code, an `answer: null` with a `refusal_reason`, or a structured `answer.kind: "refusal"`?
2. **Faithfulness eval methodology.** LLM-as-judge has known limitations (positional bias, vendor coupling). Which faithfulness metric will we adopt — verifiable claim decomposition, citation-coverage scoring, retrieval-grounded NLI, or a hybrid? Until this is decided, `/answer` quality cannot be regression-gated.
3. **Multi-turn state.** Are sessions stateful at the API level (session_id + previous QueryPlan reference) or stateless with the client carrying history? If stateful, where does state live (in-memory cache, SQLite, or KB-scoped storage)?
4. **Generation cache.** Cache key candidate: `(prompt_version, context_pack_hash, model_version)`. Eviction policy? Cache scope (global / per-KB)? Privacy interaction with the QueryPlan persistence rules in A2?
5. **Streaming schema.** SSE? Plain chunked HTTP? Structured token stream with embedded citations? How do partial responses interact with budget exhaustion?
6. **Prompt-injection handling.** Retrieved content must be treated as data, never as system/developer instructions. What is the concrete defense: content tagging, role separation, prompt template guards? How is this validated by tests?
7. **Tool-calling boundary.** Does `/answer` expose LLM tool-calling capability, or is it strictly text-in / text-out? If tool-calling is exposed, the endpoint stops being a thin wrapper and becomes part of the Agent runtime.
8. **Model/prompt versioning policy.** How are prompt and model upgrades rolled out? Generation-style shadow with eval gate, or unversioned hot-swap?

**Out of scope for this blueprint.** Selecting an LLM vendor. Defining prompt templates. Implementing tool-calling. Building any portion of `/answer` while QueryPlan / Reranker / IndexGeneration are still incomplete (T6 depends on T2 and T3).

### B7. Phase 7 — Visual Track  📋 Blueprint

Phase 7 in the archive design bundled OCR and visual embedding into one large milestone. This document splits it into two independent tracks because their cost, complexity, and value profiles are different.

#### B7A. OCR pipeline  📋 Blueprint

**Direction.** Extract text from scanned PDFs, image-based pages, and embedded images. OCR text feeds into the existing text/lexical indexes via the chunk pipeline; OCR is not a parallel retrieval path. Page snapshots produced for OCR can be reused as visual evidence assets (Phase 4–5 already supports asset attachment).

OCR is the cheaper, higher-coverage half of visual document understanding. It alone unlocks a large share of "the answer is on page X but the page is a scan" cases.

**Open questions to resolve at task start (≥4).**

1. **Layout-aware vs character-only.** Modern OCR is divided between character-level recognition (Tesseract-class) and layout-aware extraction (PP-StructureV3, dots.ocr, Read-class systems). Which class is acceptable for product manuals' typical layouts (tables, double-column, captioned figures)? What is the eval criterion for choosing?
2. **OCR backend selection criteria.** Latency, cost, accuracy on Chinese/English mixed content, table fidelity, dependency footprint, on-prem vs API. Which axes are non-negotiable?
3. **Page snapshot reuse.** OCR produces a page image plus extracted text; the same page image is also a visual evidence asset. How are snapshots deduplicated across OCR and Phase 4 evidence pipelines? Same `asset_id`, or two assets with a relation?
4. **OCR triggering policy.** Run OCR on every PDF, only on pages where `pypdf` text extraction yields nothing, or only on KBs marked as scan-heavy? Triggering interacts with rebuild cost and IndexGeneration triggers.
5. **OCR-derived chunk lineage.** OCR text re-enters the chunker. The `chunker_version` already exists; do we add `ocr_version` as a separate generation trigger, or fold it under `parser_version`? Decision affects A4 trigger conditions.

**Out of scope for this blueprint.** Choosing a specific OCR backend. Building the OCR worker. Adding OCR to the rebuild path while Phase 5 visual evidence is still settling.

#### B7B. Visual retrieval  📋 Blueprint

**Direction.** Add a visual retrieval path for queries where the user's intent is visually grounded ("show the diagram", "where is the button", "find the part labeled X"). Crucially, this is a **two-component** path:

- A visual **encoder** indexes pages or page regions into a visual vector space at index time.
- A visual **reranker** scores `(query, candidate_visual)` pairs at query time.

These are different responsibilities. The archive design conflated them. A managed visual reranker (e.g. an external multimodal API) does not remove the need for an encoder on the indexing side; without an encoder there is nothing to rerank.

**Open questions to resolve at task start (≥4).**

1. **Encoder vs reranker separation.** What is the exact handoff between encoder-produced candidates and the reranker? Top-K from visual encoder feeds into the reranker, but what K, and how does the reranker's output combine with text-retrieval scores?
2. **Encoder selection.** Late-interaction style (ColPali / ColQwen2.5-VL) vs single-vector embedding (CLIP-class / DSE / jina-clip-v2) vs none-yet (rely on caption-of-image as text). The choice has large memory/storage implications and a moving target — defer until eval data and 2026 model landscape support a decision.
3. **Train/finetune vs API-only.** Visual retrieval quality depends heavily on domain adaptation. Do we tolerate API-only deployment indefinitely, or budget for finetune capacity from day one?
4. **Score fusion with text path.** Visual scores need calibration against text scores before fusion (same principle as A3). Same calibration step? Different per-modality calibrations followed by a meta-fusion?
5. **Storage and rebuild cost.** Visual indexes are large. Generation upgrades (A4) may double the storage burden during the build window. What is the operational ceiling per KB?

**Out of scope for this blueprint.** Choosing an encoder. Choosing a reranker vendor. Building any visual indexing while QueryPlan / Reranker / IndexGeneration / OCR are still incomplete (T8 depends on T1 and T7).

### B8. Phase 8 — External Connectors  📋 Blueprint

**Direction.** Add ingestion connectors for non-file sources: DOCX, HTML, spreadsheets, and SaaS systems (Notion, Confluence, SharePoint, web exports). Connectors must produce `DocumentElement[]` and `DocumentAsset[]` directly, sharing the existing chunker / indexer / retrieval pipeline. The chunker boundary is preserved — connectors are additional parsers, not parallel pipelines.

**Open questions to resolve at task start (≥5).**

1. **Connector output contract.** Connectors emit `DocumentElement` / `DocumentAsset`, not pre-chunked content. Is the contract identical to current internal parsers, or does the connector layer need its own normalization (timezone, encoding, language tags)?
2. **Soft-delete semantics.** When the remote source removes a document, what is the local behavior — physical delete, tombstone with retention window, archive to cold storage? Does the answer differ by connector?
3. **ACL adapter.** Notion, Confluence, and SharePoint have incompatible permission models. There is no single abstraction that survives all of them. The architecture position: each connector ships its own ACL adapter that maps remote permissions onto our `doc_acl` (when introduced; not in scope here). Which permission predicates must we support uniformly?
4. **Schema drift.** Remote sources evolve (a Notion page gains a new property type). What is the connector's behavior when it encounters an unknown structure — drop, log-and-skip, log-and-store-as-opaque-metadata?
5. **Webhook vs polling.** Sync model per connector. Webhooks are cheaper but require public ingress; polling is more deployable but lossy. Default? Configurable per KB?
6. **Connector-specific eval fixtures.** Each connector ships representative fixtures before it goes to production. What is the minimum coverage bar?
7. **Credential rotation and rate limiting.** Connectors hold third-party credentials. Where do they live? How are they rotated? What is the failure mode when a connector hits a rate limit during a sync?

**Out of scope for this blueprint.** Choosing which connector to build first. Defining the SaaS-specific authentication flows. Implementing connectors before QueryPlan / IndexGeneration are in place (T9 depends on T1).

## C. Cross-cutting Principles

These two principles apply across every section of this document and across every follow-up task that this document spawns.

### C9. Eval-as-driver  🚧

**Principle.** New retrieval-affecting work begins by exercising eval, not by writing implementation. This is a mechanism, not a slogan; the mechanism is grounded in the QueryPlan persistence introduced in A2.

**Mechanism.**

1. Every `/retrieve` call produces a `QueryPlan`. Plans are persisted to per-KB SQLite (privacy-masked per A2 § Persistence).
2. A replay tool, given a generation id and an optional plan filter, re-executes the persisted plan set against the chosen generation and produces metric deltas vs the baseline (active generation).
3. New phase tasks must list, in their own PRD, which eval slices (subsets of the persisted plan set, plus any synthetic fixtures) they will exercise. The task is not eligible for `task.py start` until the eval-slice list is filled in.
4. A4 generation swap is gated on this same replay: a shadow generation is not swapped to active until the replay shows the agreed metric criteria are met.

**Replay tool contract (CLI shape, not implementation).**

```text
trellis-rag-eval replay \
  --kb <kb_name> \
  --generation g2 \
  [--baseline g1] \
  [--filter intent=table_lookup,created_after=2026-05-01] \
  [--metrics hit@5,citation_correctness,latency_p50] \
  [--output-format json|markdown]
```

The tool reads QueryPlans from SQLite, replays each against the chosen generation, computes metrics, and prints the deltas vs baseline. Implementation is owned by T5 in the roadmap below.

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
| **SQLite plan log** | `storage/sqlite_planlog.py` (new) | QueryPlan persistence per A2/D6 | 🚧 |
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
| T1 | IndexGeneration mechanism + ID system split | — | P1 | A1 + A4 combined; touches `qdrant_vector`, `state.AppState`, file layout, admin API, atomic meta.json swap |
| T2 | QueryPlan + Budget contract + SQLite plan log | T1 | P1 | A2 + D6 combined; introduces planner protocol, early-exit protocol, persistence adapter |
| T3 | Reranker first-class component + initial vendor integration | T2 | P1 | A3; defines Reranker Protocol, dispatcher, calibration step, fallback chain; first vendor concrete in Appendix A |
| T4 | WAVE repositioning + documentation honesty patch | — | P3 | A5 + C10; small task; updates operator-facing docs and code-level doc strings to match this architecture |
| T5 | eval-as-driver replay tool | T2 | P2 | C9; CLI tool, metric set, plan-filter language |
| T6 | Phase 6 `/answer` kickoff | T2, T3 | P2 | B6 (independent brainstorm; this task only enters after T2+T3 land) |
| T7 | Phase 7A OCR kickoff | T1 | P2 | B7A (independent brainstorm) |
| T8 | Phase 7B visual retrieval kickoff | T1, T7 | P3 | B7B (independent brainstorm) |
| T9 | Phase 8 connectors kickoff | T1 | P3 | B8 (independent brainstorm; connector-by-connector tasks beneath this one) |

Priority key: P1 = must precede further surface-area expansion; P2 = high-value next steps; P3 = scoped to maturation, not blocking.

T1, T2, T3 form a strict chain: T1 unlocks safe rebuilds; T2 unlocks request-level control and eval persistence; T3 turns ranking quality into a vendor-pluggable component. After T1+T2+T3 the platform is ready for `/answer` (T6) and for the visual track (T7+T8).

T4 is independent — it is documentation discipline catching up to reality and can land at any time.

T5 is the eval-as-driver enabler. It is P2 rather than P1 because the persisted plan set takes time to fill the rolling window after T2 ships; running the replay tool earlier would produce thin eval slices.

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
