# Production-grade RAG architecture and Phase 0 migration plan

## Goal

Reframe TagMemoRAG from a product-manual text retrieval engine into a production-grade, extensible RAG platform that can ingest multiple knowledge document types, preserve multimodal evidence, retrieve accurately, and provide high-quality context packages through APIs for upper-layer Agents and LLM answer generation.

The immediate lesson from the PDF chunking work is that parser/chunker behavior must not overfit to current household-appliance manuals. Product manuals remain the first business scenario, but the architecture must be designed around general document processing, evidence preservation, and production operations.

This is no longer a loose brainstorm. It is an architecture task whose first executable delivery must be intentionally small: Phase 0, stopping parser/chunker overfitting and preparing a safe migration path.

## Background / Known Context

- Current system already has useful production foundations: KB isolation, FastAPI search/rebuild endpoints, auth/rate-limit/cache modules, observability hooks, managed manual library, local/S3 blob storage, incremental rebuild, optional Qdrant vector store, evaluation fixtures, and WAVE graph retrieval.
- Current document processing is still text-chunk centric. `parse_document()` returns `Chunk` objects directly, and graph nodes store text/header/path/source metadata.
- Supported source formats are currently `.md`, `.txt`, and text-based `.pdf`.
- Recent PDF enhancement uses lightweight `pypdf` heuristics and hard-coded product-manual heading keywords. This is acceptable only as a short-term product-manual patch, not as a platform-level parsing design.
- Current search response returns text results and metadata, but not structured evidence packages, page images, figures, cropped regions, tables, or visual source assets.
- Current storage has a manual blob store, but no first-class document asset store for extracted images, page snapshots, table snapshots, OCR layers, or citation previews.
- The main production consumer is expected to be an upper-layer Agent calling RAG APIs, not only a human-facing search UI.

## Requirements

- The architecture must support multiple document families over time: PDF, scanned PDF, DOCX, HTML, Markdown, TXT, spreadsheet-like tables, images, and later knowledge-base exports.
- The ingestion pipeline must separate parsing, normalization, chunking, indexing, retrieval, evidence building, and rendering/API concerns.
- Long-term parser output must become a structured intermediate representation, not raw chunks only; the first migration step after Phase 0 is minimal Chunk Lineage IR.
- Images, page snapshots, figures, tables, captions, OCR text, and bounding boxes must be first-class retrievable/returnable evidence assets.
- Chunking must be structure-aware, sentence-aware, overlap-capable, and configurable by document profile without hard-coding one domain into core logic.
- Retrieval must support hybrid search, metadata filtering, reranking, citations, and evidence assembly.
- API contracts must eventually return evidence objects, not just flat text chunks.
- API contracts must support Agent-oriented retrieval: raw hits for debugging, evidence packages for traceability, and token-budgeted context packs for LLM prompting.
- The RAG service may later host an `/answer` endpoint with an embedded LLM, but retrieval/context APIs must remain independently usable by external Agents.
- Text evidence should ship before visual evidence so `/retrieve` can stabilize before page snapshots, crops, OCR, or image extraction are required.
- Performance budgets must be defined per phase for `/retrieve`, evidence building, context-pack assembly, asset lookup, OCR/VLM, and optional `/answer`.
- Production concerns must include tenant/KB isolation, permissions, async ingestion jobs, failure recovery, observability, eval, data lineage, and rollback.
- Product manuals remain the first scenario; generic platform support should be staged so scope does not explode.
- The mainline roadmap proceeds from Phase 0 through Phase 8. Every phase must include production readiness work for schema compatibility, eval gates, observability/debug, security/permissions, and failure degradation.

## First Delivery Scope

The first PR should implement only Phase 0.

Phase 0 means:

- Move domain-specific PDF heading keywords out of core parser logic and behind a profile/config boundary.
- Keep existing product-manual behavior available through the default product-manual profile.
- Add regression coverage that a non-appliance document does not depend on appliance vocabulary to produce reasonable chunks.
- Do not add `DocumentElement`, assets, OCR, `/retrieve`, or multimodal retrieval in the first PR.
- Update docs to make clear that the long-range design is staged and Phase 0 is only the first guardrail.

## Architecture Decisions

- `/retrieve` is the core product API for Agents. It must remain usable without any embedded LLM.
- `/answer` is optional and later-stage. It may be useful for simple clients, hosted demos, or deployments that want a managed answer endpoint, but it must not become a prerequisite for external Agents.
- If `/answer` is implemented, it must internally depend on `/retrieve`, preserve citation/evidence policy, and degrade to returning retrieval context when generation fails.

## Acceptance Criteria

- [ ] Architecture document identifies current strengths, gaps, and risks.
- [ ] Target component model separates document elements/assets/chunks/evidence.
- [ ] Roadmap defines phased migration without throwing away existing WAVE retrieval work.
- [ ] The plan explicitly covers multimodal return: extracted image, page snapshot, crop, table, citation, and fallback behavior.
- [ ] The plan defines Agent-facing API contracts for retrieval context packages and evidence references.
- [ ] The plan avoids hard-coded appliance/manual assumptions in core parser/chunker contracts.
- [ ] The first implementation phase is small enough to execute safely after design approval.
- [ ] Each implementation phase has explicit production readiness checks: schema compatibility, eval gate, observability/debug, security/permissions, and failure degradation.

## Non-Goals For This Architecture Task

- Do not implement the migration yet.
- Do not choose a heavy PDF/OCR dependency before comparing trade-offs.
- Do not claim full multimodal retrieval is required in the first implementation phase.
- Do not remove existing product-manual functionality until replacement contracts are validated.
- Do not implement Phase 1+ in the Phase 0 PR.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
