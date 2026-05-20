# Production-Grade Multimodal RAG Architecture

## Executive Position

TagMemoRAG has a strong retrieval/runtime foundation for an early product: KB isolation, managed document library, rebuild workflows, optional Qdrant, auth/cache/observability, and graph-based retrieval. The architectural weakness is upstream and downstream of retrieval:

- Upstream: document parsing collapses source files too early into text chunks.
- Downstream: search returns chunk text, not human-facing evidence packages with figures, tables, page regions, and citations.

A production RAG system should not be designed around "PDF -> text -> chunk -> vector". It should be designed around:

```text
Source Document
  -> Document Elements + Document Assets
  -> Structure-aware Chunks + Asset-derived Text
  -> Text / Metadata / Visual / Table Indexes
  -> Retrieval + Reranking
  -> Evidence Builder
  -> Agent Context Builder
  -> API Response: Context Pack + Citations + Visual Evidence
```

## Current Architecture Assessment

### Strengths Worth Preserving

- `GraphState` and WAVE retrieval provide a differentiated topology/rerank layer.
- Managed manual library already separates uploaded blobs from searchable rebuild state.
- Local/S3 blob store is a useful starting point for source files and future assets.
- Incremental rebuild and dirty tracking are important production primitives.
- API auth, rate limiting, cache, metrics, and tracing exist and should be kept.
- Evaluation framework exists and can become the quality gate for retrieval/evidence changes.

### Main Gaps

1. **No document intermediate representation**
   - Current `Chunk` is both parser output and retrieval unit.
   - This prevents preserving document structure such as paragraphs, lists, tables, figures, captions, page geometry, and OCR regions.

2. **Parser and chunker are coupled**
   - `parse_document()` decides extraction and chunking in one step.
   - This makes it hard to add DOCX/HTML/image/scanned PDF support cleanly.

3. **No first-class assets**
   - Images, page snapshots, table snapshots, and crops are not represented.
   - A mature user experience needs visual evidence, not only text citations.

4. **Chunking is not production-grade**
   - Hard splits can break sentences and tables.
   - No overlap window.
   - PDF heading detection currently includes product-manual keywords in core logic.
   - No domain profile/plugin boundary.

5. **Search result is not an evidence contract**
   - `Result` returns text, metadata, and source references.
   - It does not return source page regions, related figures, tables, or renderable asset URLs.

6. **Multimodal retrieval path is absent**
   - No OCR layer for scanned documents.
   - No image caption/index strategy.
   - No CLIP/VLM embedding abstraction.
   - No fallback hierarchy for "return crop/page if figure extraction fails".

## Target Domain Model

### Document

Represents the source file and version.

Fields:
- `doc_id`
- `kb_name`
- `source_file`
- `content_type`
- `checksum`
- `version`
- `metadata`

### DocumentElement

Parser-normalized source structure.

Fields:
- `element_id`
- `doc_id`
- `type`: `heading | paragraph | list_item | table | table_row | image_ref | caption | page | code | footnote`
- `text`
- `page_number`
- `bbox`
- `level`
- `section_path`
- `order`
- `metadata`
- `asset_refs`

### DocumentAsset

Physical or derived non-text artifact.

Fields:
- `asset_id`
- `doc_id`
- `type`: `source_file | embedded_image | page_snapshot | region_crop | table_snapshot | ocr_layer`
- `mime_type`
- `storage_uri`
- `page_number`
- `bbox`
- `width`
- `height`
- `checksum`
- `caption`
- `nearby_text`
- `ocr_text`
- `metadata`

### Chunk

Retrieval unit produced from elements, not directly from files.

Fields:
- existing fields: `text`, `header`, `path`, `level`, `source_file`, `metadata`
- new conceptual fields: `chunk_id`, `doc_id`, `element_ids`, `parent_chunk_id`, `page_start`, `page_end`, `bbox_refs`, `asset_refs`, `chunk_kind`

### Evidence

User/API-facing proof package.

Fields:
- `text`
- `source`
- `citation`
- `page_range`
- `section_path`
- `assets`
- `highlights`
- `confidence`
- `retrieval_reason`

### AgentContextPack

LLM/Agent-facing context package assembled from retrieval hits and evidence.

Fields:
- `context_id`
- `query`
- `items`
- `token_budget`
- `source_policy`
- `citation_style`
- `omitted_items`
- `warnings`

Each item should include:
- `context_item_id`
- `content`
- `content_type`: `text | table | image_caption | ocr | mixed`
- `source`
- `citation_id`
- `evidence_refs`
- `score`
- `why_selected`
- `parent_context`
- `metadata`

## ID System Overview

Production RAG depends on stable, explainable ids across rebuilds, indexes, evidence, feedback, and debug tooling. Phase 1 owns the first concrete ID derivation rules; Phase 2.5 maps those ids into index payloads.

### Persistent IDs

- `doc_id`: stable document identity. Prefer explicit metadata/library id. If absent, derive from normalized source identity plus checksum/version policy. Rename behavior must be explicit: managed-library documents should keep `doc_id` across rename; unmanaged local files may treat path rename as a new document unless sidecar metadata pins `doc_id`.
- `chunk_id`: stable retrieval-unit id derived from `doc_id`, parser/chunker version, section path, element range or synthetic element ids, page range, and normalized text fingerprint. It should replace ad hoc node-local ids in external contracts.
- `element_id`: stable source-structure id. In Chunk Lineage IR, this may be synthetic, but must be deterministic for a given parser version, source page/position, and text/table/image reference.
- `asset_id`: future stable asset id derived from `doc_id`, asset type, page/bbox or embedded-image fingerprint, source checksum, and asset-generation version.

### Runtime / Request IDs

- `node_id`: graph-local integer id. It is rebuild-local and must not be exposed as a durable external reference.
- `citation_id`: request-scoped id for a `/retrieve` response. It points to persistent ids (`chunk_id`, `doc_id`, and future `asset_id`) but is not itself durable.
- `context_item_id`: request-scoped id for Agent context-pack assembly.

### Existing Compatibility

- `chunk_identity.json` remains the compatibility bridge for rebuild reuse until `chunk_id` fully owns this role.
- Qdrant point ids should use or deterministically derive from `chunk_id` once `chunk_id` is available; before that, existing point-id behavior is preserved.
- Incremental rebuild reuse must distinguish unchanged source, metadata-only update, parser-profile change, chunker-version change, asset regeneration, and OCR regeneration.
- Old citations/debug records that reference pre-lineage `anchor_key` or `node_id` must be treated as best-effort and not promised as stable.

## Proposed Component Architecture

### 1. Connectors / Document Library

Responsibilities:
- Accept files from upload/local/S3/API.
- Track version, checksum, owner, ACL, content type, status.
- Trigger ingestion jobs.

Current modules to evolve:
- `manual_library.py`
- `manual_registry.py`
- `manual_blob_store.py`

Rename direction over time:
- `manual_*` APIs can remain for product-manual UX.
- Internal contracts should become `document_*`.

### 2. Parser Layer

Responsibilities:
- File type detection.
- Convert source into `DocumentElement[]` and `DocumentAsset[]`.
- Preserve geometry and source mapping where available.

Parser implementations:
- Markdown parser: headings, paragraphs, lists, tables, code blocks.
- TXT parser: paragraph and sentence-ish elements.
- PDF text parser: text spans, pages, headings from layout, images/page snapshots.
- Scanned PDF parser: OCR layer as optional pipeline.
- DOCX parser: headings, paragraphs, tables, images.
- HTML parser: DOM sections, tables, images, links.

Important rule:
- Domain-specific vocabulary must live in profiles/config, not in core parser logic.

### 3. Chunker Layer

Responsibilities:
- Convert element streams into retrieval chunks.
- Use structure boundaries first.
- Use sentence/list/table-aware splitting.
- Add overlap where beneficial.
- Preserve parent/child relationships.
- Create small retrieval chunks and optional parent context chunks.

Chunking strategies:
- `section_chunker`: headings and section path.
- `sentence_window_chunker`: paragraph/sentence windows with overlap.
- `table_chunker`: row-wise semantic expansion with table header context.
- `visual_context_chunker`: captions/OCR/nearby text linked to assets.
- `hierarchical_chunker`: child chunks for retrieval, parent chunks for answer context.

### 4. Indexing Layer

Responsibilities:
- Embed text chunks.
- Index lexical terms.
- Index metadata/facets.
- Optionally index image captions/OCR and visual embeddings.
- Persist graph, vectors, assets, and lineage.

Indexes:
- Text vector index.
- Lexical/BM25-like index.
- Metadata/facet index.
- Graph topology index.
- Asset text index.
- Optional image vector index.

### 5. Retrieval Layer

Responsibilities:
- Query understanding.
- Metadata narrowing/boosting.
- Hybrid retrieval.
- Reranking.
- Graph propagation.
- Dedup and diversity.

Needed additions:
- Query intent classification: answer text vs show diagram vs find table vs troubleshoot.
- Evidence-aware retrieval: prefer chunks with relevant assets for visual/how-to queries.
- Table/code/model-number-aware retrieval.

### 6. Evidence Builder

Responsibilities:
- Convert chunk hits into user-facing evidence.
- Fetch parent context, related elements, and assets.
- Generate page/region URLs.
- Crop page regions when direct figure extraction is unavailable.
- Return fallbacks predictably.

Evidence fallback ladder:
1. Exact figure/image asset attached to hit.
2. Region crop around relevant element bbox.
3. Page snapshot with highlighted region.
4. Original source file page reference.
5. Text-only citation.

### 7. Agent Context Builder

Responsibilities:
- Convert ranked hits and evidence into a compact context package for upper-layer Agents/LLMs.
- Deduplicate overlapping chunks.
- Merge adjacent chunks from the same section/page when it improves answerability.
- Keep strict source/citation ids attached to every context item.
- Respect token budgets.
- Preserve tables in model-readable form.
- Include image captions/OCR/nearby text for text-only LLMs while preserving `asset_refs` for multimodal LLMs.
- Separate "retrieved text" from "model instructions"; the RAG layer should not smuggle prompt behavior into evidence content.

The Agent should not consume raw top-k chunks by default. It should consume a structured `context_pack` with source lineage and evidence references.

Example:

```json
{
  "context_pack": {
    "token_budget": 4000,
    "items": [
      {
        "context_item_id": "ctx_001",
        "content_type": "text",
        "content": "Clean the lower filter after opening the service cover...",
        "source": {
          "doc_id": "manual_123",
          "source_file": "washer.pdf",
          "page_range": [32, 33],
          "section_path": ["Maintenance", "Cleaning the filter"]
        },
        "citation_id": "cit_001",
        "evidence_refs": ["ev_001"],
        "score": 0.91,
        "why_selected": "Matched filter-cleaning procedure and same model metadata."
      }
    ]
  }
}
```

### 8. Answer / API Layer

Responsibilities:
- Provide stable API for Agents first, and UI/humans second.
- Return `context_pack`, `evidence`, `citations`, `results`, and `debug` separately.
- Optionally provide `/answer` later by embedding an LLM, but keep `/retrieve` independent so external Agents can call the RAG service directly.
- Avoid leaking internal filesystem paths; return signed or routable asset URLs.

API direction:

- `POST /retrieve`: primary Agent API; returns raw hits, evidence, and `context_pack`.
- `POST /search`: compatibility/debug endpoint; may continue returning flat text results.
- `POST /answer`: optional future endpoint; internally calls `/retrieve`, then invokes configured LLM.
- `GET /assets/{asset_id}` or signed URL endpoint: serves visual evidence with authorization.

`/retrieve` response direction:

```json
{
  "query": "...",
  "context_pack": {
    "items": []
  },
  "results": [],
  "evidence": [
    {
      "evidence_id": "ev_001",
      "text": "...",
      "source_file": "manual.pdf",
      "page_range": [12, 13],
      "section_path": ["Maintenance", "Filter cleaning"],
      "assets": [
        {
          "asset_id": "asset_...",
          "type": "region_crop",
          "url": "/assets/asset_...",
          "caption": "Filter removal diagram",
          "page_number": 12,
          "bbox": [120, 240, 360, 180]
        }
      ]
    }
  ],
  "debug": {}
}
```

## Production Capabilities Checklist

- Multi-format ingestion.
- Async ingestion/rebuild jobs.
- Incremental parse/embed/index reuse.
- Stable ID strategy for documents, chunks, synthetic elements, assets, citations, graph nodes, and vector-store point ids.
- Asset storage with local/S3 backend.
- Secure asset serving/signed URLs.
- Tenant/KB-level access control.
- Observability for parsing, chunking, embedding, retrieval, rerank, answer generation.
- Evaluation sets for retrieval hit rate, citation correctness, context sufficiency, token-budget adherence, table retrieval correctness, visual evidence correctness, insufficient-evidence/no-answer behavior, metadata narrowing correctness, and regression.
- Agent-facing retrieval evals must check whether `context_pack` is sufficient for an LLM to answer correctly before answer generation is introduced.
- Failure isolation: bad document does not break whole KB unless configured strict.
- Versioned schemas and migrations.
- Phase-level latency and cost budgets for retrieval, evidence/context assembly, asset lookup, OCR/VLM, and answer generation.
- Admin operations: reprocess document, reindex assets, rebuild one document, inspect parse output.
- Privacy controls: no raw query/vector/snippet leakage in debug logs.

## Migration Roadmap

Every phase below must ship with the same production readiness checklist:

- **Schema compatibility**: versioned fields, backward-compatible defaults, migrations or compatibility adapters where needed.
- **Eval gate**: focused regression/eval criteria that must pass before the phase is considered done.
- **Baseline comparison**: phases that alter parsing, chunking, indexing, retrieval, evidence, or context construction must compare against stored eval baselines and document intentional trade-offs.
- **Observability/debug**: metrics, logs, traces, or debug payloads sufficient to diagnose phase-specific behavior without leaking sensitive content.
- **Security/permissions**: KB/tenant access checks, asset access checks when applicable, no raw secrets or unsafe paths in responses.
- **Failure degradation**: explicit fallback behavior when parsing, indexing, retrieval, asset extraction, OCR, or LLM calls fail.

### Phase 0: Stop Overfitting

- Mark current PDF heuristics as product-manual profile behavior.
- Remove hard-coded domain vocabulary from core parser path.
- Add tests proving non-appliance docs do not collapse because of missing appliance keywords.
- Unknown explicitly configured parser profiles must fail fast with a clear config error; missing profile uses the backward-compatible default.
- Production checks: parser profile config is backward-compatible; eval gate covers product-manual and generic docs; debug can expose selected parser profile; profile failures fall back to generic/page fallback safely.

### Phase 1: Chunk Lineage IR

- Add the minimum lineage fields needed for future evidence building without requiring a complete document intelligence layer.
- Preserve existing `Chunk` and graph builder behavior.
- Store lineage in chunk metadata: `doc_id`, `element_ids`, `page_start`, `page_end`, `section_path`, `asset_refs`, `parser_profile`, and `parser_version`.
- Allow `element_ids` and `asset_refs` to be empty or synthetic in the first implementation.
- Do not require durable `DocumentElement` / `DocumentAsset` storage in this phase.
- Define stable ID derivation for `doc_id`, `chunk_id`, synthetic `element_ids`, and future `asset_id`, including rebuild, rename, metadata-only update, and chunker-version-change behavior.
- Define how existing `chunk_identity.json`, Qdrant point ids, persistent chunk ids, and request-scoped citation ids relate to each other.
- Production checks: metadata schema remains backward-compatible; eval confirms lineage presence and old search clients still work; debug can show lineage coverage counts; missing lineage degrades to existing source/page metadata.

### Phase 2: Production Chunker

- Add sentence-aware splitting.
- Add configurable overlap.
- Add Markdown table semantic expansion.
- Add hierarchical child/parent chunks.
- Add profiles for product manuals without hard-coding domain terms.
- Production checks: chunk identity compatibility is protected or migration is explicit; eval covers retrieval hit rate, table correctness, and chunk boundary regressions; metrics report chunk counts/split reasons; bad chunker config falls back to safe defaults.

### Phase 2.5: Indexing Strategy and Index Schema

- Decide graph node granularity: child chunks as retrievable graph nodes; parent chunks as optional context expansion unless explicit eval proves parent vector nodes help.
- Define whether parent chunks, table semantic chunks, table rows, OCR text, image captions, and asset-derived text enter vector, lexical, metadata/facet, graph, or asset indexes.
- Define Qdrant payload schema for `doc_id`, `chunk_id`, `section_path`, `page_start`, `page_end`, `asset_refs`, chunk kind, parser profile, and parser version.
- Define how hybrid retrieval combines text vector, lexical, metadata, graph, table, asset-text, and later visual scores.
- Initial hybrid fusion should remain explainable and conservative; learned or complex score fusion is deferred until eval data is sufficient.
- Add a fusion exploration plan: start with pipeline/weighted-score fusion using explicit debug components, compare against reciprocal-rank-fusion or simple normalized weighted fusion, then consider learned fusion only after sufficient labeled eval/feedback data exists.
- Every fusion experiment must report retrieval quality, citation quality, latency, debuggability, and failure behavior before replacing the conservative default.
- Define incremental rebuild reuse rules for each index: unchanged source, metadata-only update, chunker-version change, asset regeneration, OCR regeneration, and connector sync.
- Production checks: index schemas are versioned; eval gate proves no baseline retrieval regression; debug exposes index participation and score components without leaking raw text; index failures degrade to the safest available index path.

### Phase 3: Text Evidence and Agent Context API

- Add text-only evidence builder.
- Add citation ids, matched chunk ids, source file, page range, section path, text snippet, confidence, and retrieval reason.
- Add Agent context builder for token-budgeted `context_pack`.
- Add `/retrieve` response with `context_pack`, text evidence, citations, raw results, and debug.
- Keep old `/search` result shape compatible.
- Do not require visual assets yet.
- Add minimal query intent classification for `text_answer`, `table_lookup`, `troubleshooting`, `model_specific`, `out_of_scope`, and future `visual_reference`.
- Define `/retrieve` API compatibility policy: `schema_version`, stable fields, optional additive fields, debug as non-contract, raw-results/evidence relationship, and client version annotation or negotiation.
- Expose insufficient-evidence signaling for Agents: answerability, confidence, warnings, fallback reason, and conflicting evidence where applicable.
- Define latency budgets for `/retrieve`, including retrieval, text evidence building, context-pack assembly, debug payload construction, and cache behavior.
- Production checks: `/retrieve` schema is versioned; eval covers citation correctness, context sufficiency, token budget adherence, and no-answer/insufficient-evidence behavior; debug separates raw hits/evidence/context decisions; permissions match `/search`; failures return text-only/empty-evidence responses with explicit reasons.

### Phase 3.5: Admin Inspection, Debug Artifacts, and Feedback Loop

- Add admin/inspect support for parsed chunks, lineage fields, evidence decisions, context-pack selection, omitted chunks, and citation generation.
- Add debug artifacts for focused local diagnosis without exposing raw sensitive text in public logs.
- Add lightweight retrieval feedback telemetry: query hash, `kb_name`, selected evidence ids, selected context item ids, user/Agent feedback, failure reason, and no-answer flag.
- Use feedback to identify bad citations, insufficient contexts, unhelpful chunks, documents needing reparse, and candidates for new eval cases.
- Production checks: inspect APIs require admin permissions; feedback schema is privacy-preserving and versioned; eval snapshots can be generated from approved failures; failures in feedback logging never break retrieval.

### Phase 4: Visual Evidence Pipeline

- Extract PDF page snapshots.
- Extract embedded images where feasible.
- Generate region crops from bboxes.
- Store assets in local/S3 asset store.
- Add asset-serving endpoint with access checks.
- Define asset lifecycle: cleanup orphan assets, handle deleted/disabled documents, version replacement, temporary asset cleanup after failed rebuilds, checksum deduplication, retention policy, metadata migration, and local/S3 consistency checks.
- Asset access must be authorized against the same KB/document permission context that produced the evidence.
- Production checks: asset schema is versioned and storage backend-compatible; eval covers asset extraction coverage; metrics track asset extraction/store failures; asset URLs enforce KB/tenant permissions; extraction failures degrade to source page references.

### Phase 5: Visual Evidence API

- Extend evidence builder with page snapshots, region crops, table snapshots, embedded images, and OCR-layer references.
- Return text + citations + assets through `/retrieve`.
- Add UI-facing URLs, page numbers, bbox/highlight metadata.
- Extend query intent handling for visual requests such as show diagram, find button, where is part, and show installation layout.
- Define visual evidence latency budgets and fallback rules for asset lookup, crop generation, and signed URL generation.
- Production checks: evidence asset fields are optional/backward-compatible; eval covers visual evidence correctness; debug shows why assets were attached or omitted; unauthorized assets are never returned; missing assets degrade to text evidence.

### Phase 6: Optional Answer API

- Add `/answer` only after `/retrieve` contracts are stable.
- `/answer` is a convenience/hosted-generation endpoint, not the core Agent integration contract; `/retrieve` remains the primary API.
- Internally call `/retrieve`, then pass `context_pack` to configured LLM.
- Keep external Agent path supported; `/answer` is convenience, not the only integration mode.
- Evaluate answer faithfulness against citations and evidence refs.
- Define answer governance: prompt version, model config version, citation policy, source-only answering policy, answer language policy, streaming support, answer cache policy, token/cost tracking, generated answer audit, and prompt-injection handling.
- Define answer latency and cost budgets separately from `/retrieve`.
- Treat retrieved content strictly as data, never as system/developer instructions.
- Production checks: answer schema is versioned separately from retrieve; eval covers faithfulness and refusal on insufficient evidence; traces separate retrieve latency and LLM latency; model/API keys never leak; LLM failures degrade to `/retrieve` context output.

### Phase 7: OCR / Visual Retrieval

- Add optional OCR backend for scanned PDFs and images.
- Add image caption/VLM pipeline as optional.
- Add visual embedding index only after text+asset evidence path is stable.
- OCR, VLM, and visual embedding are optional, disabled by default, and controlled per KB/profile with cost and latency limits.
- Production checks: OCR/visual fields are optional and versioned; eval covers OCR quality and visual retrieval correctness; metrics report OCR/VLM failures and costs; asset permissions propagate to OCR/visual outputs; failures degrade to page snapshot or text-only retrieval.

### Phase 8: Broader Knowledge Connectors

- Add DOCX/HTML/spreadsheet parsers.
- Add web/export connectors as separate ingestion plugins.
- Add connector-specific metadata normalization.
- Connectors must define sync, deletion sync, cursor/checkpoint, credential rotation, rate limits, fetch retry, deduplication, source permission mapping, moved/renamed remote document behavior, and connector-specific eval fixtures before production use.
- Production checks: connector schemas are normalized to common document contracts; eval covers each connector's representative docs; observability reports connector-specific parse/fetch failures; connector credentials and ACLs are isolated; failed connectors do not poison healthy KBs.

## First Implementation Recommendation

Do not start with heavy OCR or multimodal embeddings.

Start with a safe architectural foundation:

1. Complete Phase 0 by moving domain-specific parser hints behind profiles/config.
2. Add Chunk Lineage IR: `doc_id`, `element_ids`, `page_start`, `page_end`, `section_path`, `asset_refs`, `parser_profile`, and `parser_version`.
3. Define stable IDs and the index schema before expanding chunk/entity types.
4. Add sentence-aware split + overlap.
5. Add Markdown table semantic chunks.
6. Add text-only evidence and `/retrieve` before visual evidence.

This creates the shape of a production system without overcommitting to expensive dependencies.

## Key Architecture Principle

The unit of retrieval is a chunk, but the unit of user trust is evidence. The system must optimize for evidence quality, not only top-k chunk scores.
