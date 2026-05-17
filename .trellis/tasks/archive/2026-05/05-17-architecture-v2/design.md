# Architecture v2 — Task Design

This document is the design of the **task that produces** `.trellis/spec/backend/architecture.md`. It is not the architecture itself. It defines: what to write, how to structure it, what each section must contain, and how to validate the result against the six brainstorm decisions (D1–D6).

## Boundaries

**In scope**

- Drafting `.trellis/spec/backend/architecture.md` v1 (the living doc).
- Updating `.trellis/spec/backend/index.md` to point at the new living doc.
- Producing the follow-up execution roadmap inside the new architecture.md.

**Out of scope**

- Modifying production code under `src/tagmemorag/`.
- Modifying any archived task file under `.trellis/tasks/archive/`.
- Creating any follow-up Trellis task via `task.py create`.

## Document Structure (target)

`architecture.md` is organized as follows. Section status markers follow D1: ✅ implemented, 🚧 under v2 revision, 📋 blueprint.

```
# TagMemoRAG Architecture (living doc)

## Document Status
- version, supersedes, last_updated, owner
- relationship to archive/production-rag-architecture/design.md

## Reading Guide
- Status legend (✅ / 🚧 / 📋)
- Where to find what (Phase 0–5 details, Phase 6–8 blueprints, follow-up roadmap)

## Executive Position
- Honest assessment of where the system stands today (no "production-grade" self-label)
- Three production-blocking gaps named explicitly: QueryPlan, Reranker, IndexGeneration

## System Overview
- Pipeline diagram (Source → Element/Asset → Chunk → Index → Retrieve → Rerank → Evidence → ContextPack → API)
- Per-stage status markers

## Domain Model
- Document, DocumentElement, DocumentAsset, Chunk, Evidence, AgentContextPack
- ID system: persistent IDs vs request-scoped IDs vs runtime IDs

## A. Currently Implemented (Phase 0–5) — with v2 revisions

### A1. ID System Split (🚧)
- Before: chunk_id includes nothing about embedding; vector_point_id implicit
- After: chunk_id is logical identity; vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)
- Migration shape: handled by IndexGeneration (A4)
- Open implementation question: which existing call sites need adapter

### A2. QueryPlan + Request Budget (🚧)
- QueryPlan schema (rewrites, intent, filters, strategy, rerank spec, budget)
- Budget schema (latency_ms, rerank_tier, max_evidence, allow_external_reranker)
- Early-exit protocol shape
- Persistence: SQLite per-KB (D6)

### A3. Reranker as First-Class Component (🚧)
- Reranker Protocol (id, version, max_seq_length, supports_instruction)
- Cache key composition
- Tier classification (online tier-1, offline teacher, fallback chain)
- Calibration requirement before fusion
- Failure semantics: timeout → tier downgrade → noop, never error
- (Reference implementation lives in appendix per D4)

### A4. IndexGeneration (🚧)
- Naming: `{prefix}_{kb}_g{N}` for Qdrant; `{kb}/g{N}/...` for files
- AppState holds active + shadow generations
- Trigger fields (parser_version / chunker_version / embedding_model_id / embedding_model_version / index_schema_version)
- Admin API shape (build-shadow, swap, retire)
- Rollback boundary: swap is reversible until retire
- Real-flow comparison NOT via traffic split; via offline replay of persisted plans (links to A2 + C9)

### A5. WAVE Repositioning (🚧)
- Moved from "Strengths Worth Preserving" to "Experimental — default off"
- Reason: empirical 3/3 KEEP_OFF (memory: wave-readiness-flags-empirical-keep-off)
- Promotion criteria: reproducible green on a defined production-eval slice

## B. Blueprints (Phase 6–8) — direction + open questions (D2)

### B6. Phase 6 — /answer endpoint (📋)
- Direction (one paragraph)
- Open questions to resolve at task start
- What we will NOT do here

### B7. Phase 7 — Visual Track (📋)
- 7A OCR (📋): direction, open questions, layout-aware vs char-only is an open question
- 7B Visual retrieval (📋): direction, encoder vs reranker separation, SF VL-Reranker-8B noted as one option in appendix
- Open questions to resolve at task start

### B8. Phase 8 — Connectors (📋)
- Direction
- Open questions: DocumentElement output contract, soft-delete, ACL adapter, schema drift, webhook vs polling

## C. Cross-cutting Principles

### C9. eval-as-driver
- Every /retrieve QueryPlan is a candidate eval sample (after privacy mask, D6)
- New phase entry MUST start by generating eval cases from persisted plans
- Replay mechanism: A4 active vs shadow comparison runs on persisted plan set

### C10. Documentation Honesty
- WAVE is not a strength until proven (A5)
- "production-grade" self-label is replaced by explicit gap naming
- Vendor pricing/limits live only in appendix (D4)

## Storage Backends
- json_* / npz_* / qdrant_* (existing)
- sqlite_planlog (new, for D6 QueryPlan persistence)

## Follow-up Execution Roadmap
- Table of follow-up tasks: id, title, dependencies, priority, expected scope
- (D3: not pre-created via task.py; just listed)

## Appendix A — Reference Implementations (as of YYYY-MM-DD)
- Reranker reference: SF Qwen3-Reranker-0.6B online, Qwen3-Reranker-8B offline teacher, BGE/BCE fallback
- Visual reference: SF Qwen3-VL-Reranker-8B as one option for B7's reranker tier
- All vendor-specific pricing/limits/model-ids confined here

## Appendix B — Changelog vs production-rag-architecture archive
- Section-by-section diff at high level (what changed, what stayed)
- For full historical context see archived design.md
```

## Section-by-Section Content Spec

For each `architecture.md` section the writer must produce, this lists the minimum substance.

### Document Status

```yaml
version: 2.0
supersedes: .trellis/tasks/archive/2026-05/05-17-production-rag-architecture/design.md
last_updated: 2026-05-17
owner: suixingchen
status: living
related_tasks_archive: 05-17-architecture-v2
```

A short paragraph: this is the single source of truth; the archived design is preserved as historical reference but no longer authoritative.

### A1 ID System Split — required substance

- Before-section: paste current chunk_id derivation pseudocode from archive design (parser_version, chunker_version, section_path, element_range, page_range, text_fingerprint).
- After-section:
  - `chunk_id = hash(doc_id, parser_version, chunker_version, section_path, element_range, page_range, text_fingerprint)` (unchanged)
  - `vector_point_id = hash(chunk_id, embedding_model_id, embedding_model_version)` (new)
  - `reranker_id` does NOT enter any persistent ID
- Migration: changing embedding model invalidates only `vector_point_id`; chunk_id stable across embedder swap. Coexistence is enabled by A4 (separate Qdrant collections per generation).
- One-line implementation hint: `qdrant_vector.collection_name(prefix, kb)` extends to `(prefix, kb, generation)`; chunk_id derivation lives in chunk lineage code path.

### A2 QueryPlan + Budget — required substance

Schemas (Python-style typed dataclass, not actual code):

```python
@dataclass
class Budget:
    latency_ms: int
    rerank_tier: Literal["off", "tier1", "tier2"]
    max_evidence: int
    allow_external_reranker: bool

@dataclass
class RerankSpec:
    reranker_id: str
    reranker_version: str
    instruction: str | None
    top_n: int

@dataclass
class QueryPlan:
    schema_version: int
    plan_id: str
    kb_name: str
    query_hash: str
    query_rewrites: list[str]
    intent: Literal["text_answer", "table_lookup", "troubleshooting",
                    "model_specific", "visual_reference", "out_of_scope"]
    filters: dict
    strategy: dict
    rerank: RerankSpec | None
    budget: Budget
    served_by_generation: int | None
    created_at: str
```

Early-exit protocol: each downstream component reads `budget.latency_ms`, returns whatever it has so far if exceeded; final response carries `warnings: ["<component>_skipped_due_to_budget"]`.

Persistence (links to D6): SQLite per-KB. raw query NOT stored; rewrites stored after PII mask.

### A3 Reranker — required substance

`Reranker` Protocol contract (vendor-neutral):

```python
class Reranker(Protocol):
    id: str
    version: str
    max_seq_length: int
    supports_instruction: bool
    def rerank(self, query: str, docs: list[RerankDoc],
               instruction: str | None, budget_ms: int) -> RerankResult: ...
```

Cache key: `(reranker_id, reranker_version, instruction_hash, normalized_query, chunk_id_set_hash)`.

Tier table (abstract, no vendors):

| Tier | When used | Default state |
|---|---|---|
| Tier-1 online | /retrieve main path | ON |
| Tier-2 online | high-value queries / experiments | OFF |
| Offline teacher | eval ground truth + Tier-1 distillation | — |
| Fallback chain | SF outage / private KB | configurable |
| Noop | total failure | always available |

Calibration requirement: `relevance_score` is not assumed normalized; before hybrid fusion the score must pass through a calibration step. Choice of calibration (z-score / min-max / sigmoid) is a Phase 2.5 fusion experiment, not specified here.

Document truncation rule: when reranker does not support `max_chunks_per_doc`, the caller truncates each doc to `reranker.max_seq_length - query_token_budget - instruction_token_budget`. The exact reserved budgets are kept in appendix.

ACL gate: `budget.allow_external_reranker == False` → reranker calls bypass external vendor and route to a local/fallback implementation only.

### A4 IndexGeneration — required substance

State machine:

```
   [empty]
      │ build
      ▼
   [g1 active]
      │ build shadow
      ▼
   [g1 active, g2 shadow]
      │ swap         │ rollback (before retire)
      ▼              ▲
   [g1 retired*, g2 active]
      │ retire
      ▼
   [g2 active]
```

`* retired = still on disk until explicit retire admin call`

Storage layout:

```
{kb_root}/
  meta.json          # active_generation, shadow_generation, history
  g1/
    graph.json
    vectors.npz / qdrant_pointer
    chunk_identity.json
    assets/
  g2/
    ...
```

Qdrant collection name: `{prefix}_{kb}_g{N}`.

Admin API shape (REST):

- `POST /admin/generation/build-shadow` → starts background rebuild into next g{N+1}
- `POST /admin/generation/swap` → atomic swap of active and shadow pointer in `meta.json`
- `POST /admin/generation/retire` → frees disk for retired generation
- `GET  /admin/generation/status` → current active, shadow, build progress

Trigger conditions for new generation: any of `parser_version`, `chunker_version`, `embedding_model_id`, `embedding_model_version`, `index_schema_version` changes.

Rollback boundary: swap is reversible (just swap pointers back) until retire; after retire the previous generation is gone.

Real-flow comparison: NOT via traffic split. Mechanism = replay persisted QueryPlans against shadow, compare to active baseline. Lives under C9.

### A5 WAVE Repositioning — required substance

Move WAVE from "Strengths Worth Preserving" to "Experimental — default off".

Status statement to include:
- 3 readiness flags empirically evaluated 2026-05-17, all KEEP_OFF.
- Code retained for research / future revisit.
- Not on the critical retrieval path; default behavior unaffected by WAVE.
- Promotion criteria explicit: reproducible improvement on a defined production-eval slice.

Cross-link memory: `wave-readiness-flags-empirical-keep-off`.

### B6/B7/B8 — required substance per blueprint

Each section follows the D2 template:

```
### B<N>. <Phase Title>  📋 Blueprint

**Direction** (1 paragraph)
What we are aiming at, why now (or why not now), and how it relates to A1–A5.

**Open Questions to resolve at task start**
1. <question>
2. <question>
…

**Out of Scope for this blueprint**
- <decisions deliberately deferred>
```

Minimum question count per phase:
- B6: ≥6 (multi-turn state, refusal contract, faithfulness eval, generation cache, streaming schema, prompt-injection handling)
- B7A: ≥4 (layout-aware vs char-only, OCR backend selection criteria, page snapshot reuse, OCR triggering policy)
- B7B: ≥4 (encoder vs reranker separation, encoder selection, training/finetune vs API-only, score fusion with text path)
- B8: ≥5 (DocumentElement output contract, soft-delete semantics, ACL adapter, schema drift handling, webhook vs polling)

### C9 eval-as-driver — required substance

- Define mechanism, not slogan: persisted QueryPlan rows in SQLite + replay tool.
- Replay tool contract (CLI shape, not implementation): given a generation id and an optional plan filter, produces metrics deltas vs active.
- Eval data lifecycle: rolling window (default 30 days), retention configurable per KB.
- New phase entry rule: phase task PRD must list which eval slices it will exercise before implementation.

### C10 Documentation Honesty — required substance

- Rule: any "production-grade" self-claim must be replaced by explicit naming of either implemented capability or a remaining gap.
- Rule: vendor names, model ids, prices, limits live only in Appendix A.
- Rule: experimental features default off and are listed in a single "Experimental" subsection at the end of the relevant section.

### Storage Backends — required substance

Subsection table:

| Backend | Module | Role |
|---|---|---|
| JSON graph | storage/json_graph | graph topology |
| JSON anchor | storage/json_anchor | anchors |
| NPZ vector | storage/npz_vector | vectors (default) |
| Qdrant vector | storage/qdrant_vector | vectors (optional, generation-aware) |
| SQLite plan log | storage/sqlite_planlog (new) | QueryPlan persistence |
| Local/S3 blob | storage/blob | source files + assets |

`sqlite_planlog` notes:
- per-KB file path: `{kb}/query_plans.db`
- schema versioning via `PRAGMA user_version`
- no ORM; stdlib `sqlite3` only

### Follow-up Execution Roadmap — required substance

Table format:

| ID | Title | Depends on | Priority | Scope hint |
|---|---|---|---|---|
| T1 | IndexGeneration mechanism + ID split | — | P1 | A1 + A4 combined |
| T2 | QueryPlan + Budget contract + SQLite plan log | T1 | P1 | A2 + D6 combined |
| T3 | Reranker first-class + SF Qwen3-0.6B integration | T2 | P1 | A3 |
| T4 | WAVE repositioning + doc honesty patch | — | P3 | A5 + C10 (small) |
| T5 | eval-as-driver replay tool | T2 | P2 | C9 |
| T6 | Phase 6 /answer kickoff (independent brainstorm) | T2, T3 | P2 | B6 |
| T7 | Phase 7A OCR kickoff | T1 | P2 | B7A |
| T8 | Phase 7B visual retrieval kickoff | T1, T7 | P3 | B7B |
| T9 | Phase 8 connectors kickoff | T1 | P3 | B8 |

This is the scaffold; D3 says no `task.py create` until each task is actually started.

### Appendix A — Reference Implementations (as of 2026-05-17)

- Endpoint: `POST https://api.siliconflow.cn/v1/rerank`
- Online tier-1: `Qwen/Qwen3-Reranker-0.6B`, 32K context, ¥0.07/M input tokens, L0 RPM 2000 / TPM 1M, supports `instruction`.
- Offline teacher: `Qwen/Qwen3-Reranker-8B`.
- Fallback: `Pro/BAAI/bge-reranker-v2-m3` (supports `max_chunks_per_doc`, `overlap_tokens`).
- Visual reranker option (B7B): `Qwen/Qwen3-VL-Reranker-8B`, 32K context.
- Truncation: Qwen3 family does NOT support `max_chunks_per_doc`/`overlap_tokens`; caller must pre-truncate.
- Score field: `relevance_score`; normalization not guaranteed; calibration required before fusion.

Each appendix subsection ends with: "These details may change without code changes; only this appendix needs an update."

### Appendix B — Changelog vs archive

A single table:

| Topic | Archive design (Phase 0 task) | architecture.md v2 |
|---|---|---|
| WAVE | Listed as strength | Experimental, default off |
| chunk_id | Single-layer derivation | Two-layer: chunk_id vs vector_point_id |
| Reranker | Mentioned in Phase 2.5 prose | First-class component, tier table |
| IndexGeneration | Implicit in rebuild | Named mechanism with state machine |
| QueryPlan | Absent | New cross-cutting layer |
| Phase 7 | Bundled OCR + visual embedding | Split into 7A (OCR) + 7B (visual reranker) |
| Vendor specifics | Mixed in text | Confined to Appendix A |
| "production-grade" | Used as self-label | Replaced by explicit gap naming |

## index.md Update

After `architecture.md` is in place, update `.trellis/spec/backend/index.md`:

- Add a top-level link to `architecture.md` as the primary source.
- Demote the `production-rag-architecture` archive references to a "Historical references" subsection.
- Keep the existing per-topic guideline links (directory-structure, database-guidelines, etc.) unchanged.

## Validation

`architecture.md` passes if all the following hold:

1. Every section listed under "Document Structure" exists with the required substance.
2. Status markers (✅/🚧/📋) used correctly per the legend.
3. No occurrence of standalone "production-grade" as a self-label (search test).
4. All vendor-specific identifiers (`Qwen3-Reranker-0.6B`, `siliconflow`, prices, RPM, TPM) appear only inside Appendix A (search test).
5. WAVE section explicitly lists the empirical KEEP_OFF result and links the memory.
6. Follow-up roadmap table contains rows T1–T9 with `Depends on` and `Priority` filled.
7. `index.md` updated to reference the living doc.

`git diff --check` passes; spec lint (if any) passes.

## Risks / Tradeoffs

- The doc is long. Mitigation: each section can be read in isolation; status markers help skimming.
- Reference appendix can drift from reality. Mitigation: dated header on appendix; T3 task will refresh it as part of integrating the reranker.
- D2 chosen depth means B6–B8 sections look "thin" compared to A sections. This is by design; readers should treat them as kickoff material, not specs.

## Rollout / Rollback

This is a documentation task — no production code changes. Rollback = revert the doc files (`architecture.md`, `index.md`).
