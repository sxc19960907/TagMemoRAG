# Phase 2: Production Chunker

## Goal

Upgrade TagMemoRAG chunking from simple heading/blank-line splitting plus hard character cuts into a production-oriented chunking layer that improves product-manual retrieval now while preserving the path toward a general RAG platform.

The task should not chase the entire architecture roadmap. It should deliver the smallest useful chunker improvements after Phase 1 lineage: sentence-aware splitting, configurable overlap, table-aware preservation/expansion for Markdown-like tables, and explicit chunk metadata needed for later indexing/evidence phases.

## Background / Known Context

- Phase 0 introduced parser profiles so product-manual PDF heading hints are no longer core parser behavior.
- Phase 1 added chunk lineage metadata: `doc_id`, `chunk_id`, `element_ids`, `section_path`, `asset_refs`, `parser_profile`, and `parser_version`.
- Current `_hard_split()` still slices text every `max_chars`, which can cut sentences and damage embedding quality.
- Current chunking has no overlap, so relevant facts can be split across adjacent chunks with no local context.
- Current Markdown tables are treated as ordinary text; table headers/rows are not made easier to retrieve.
- Current product priority remains: make product manuals work well first. The implementation must avoid appliance-specific hard-coding and keep future document families possible.

## Direction Gates

Every major step must explicitly check whether the work still follows the main direction:

- **Gate 0: Before implementation** — confirm the task scope is still product-manual-first, platform-safe, and does not implement `/retrieve`, visual assets, OCR, or full Document IR.
- **Gate 1: After chunker core changes** — inspect output on representative Markdown/TXT/PDF fixtures and verify the new behavior improves boundaries without domain-specific vocabulary.
- **Gate 2: Before commit/archive** — compare tests/eval against baseline and document any intentional trade-offs in chunk count, latency, or retrieval quality.

## Requirements

- Add sentence-aware splitting for oversized text blocks.
- Add configurable chunk overlap with safe defaults.
- Preserve existing parser profiles and Phase 1 lineage fields.
- Ensure split chunks receive distinct deterministic `chunk_id`s after post-processing.
- Add table-aware handling for Markdown pipe tables:
  - keep full small tables intact when possible;
  - avoid cutting table rows in the middle;
  - add simple table metadata or semantic expansion only when it remains deterministic and profile-neutral.
- Add chunk metadata needed by Phase 2.5 indexing decisions, such as chunk kind or split reason if useful.
- Keep `/search` response backward-compatible; new fields must be additive metadata.
- Keep `chunk_identity.json` compatibility protected by parser/chunker signature changes or explicit migration behavior.
- Maintain product-manual behavior while proving the implementation is not appliance-specific.

## Production Readiness

- **Schema compatibility**: new chunk metadata is additive; existing clients and graph storage remain load-compatible.
- **Eval gate**: parser/chunker tests, full test suite, and eval CI must pass. Any retrieval metric regression must be documented and justified.
- **Observability/debug**: chunk split reasons, overlap behavior, and table handling should be inspectable through metadata or bounded debug artifacts without leaking extra raw text in logs.
- **Security/permissions**: IDs and metadata must not expose absolute paths, secrets, or raw file-system internals.
- **Failure degradation**: invalid chunker config fails clearly or falls back to safe defaults; malformed tables degrade to ordinary text chunks.

## Acceptance Criteria

- [ ] Oversized chunks split on sentence/paragraph boundaries when possible instead of arbitrary character cuts.
- [ ] Configurable overlap is applied deterministically and does not create duplicate `chunk_id`s.
- [ ] Markdown table fixtures preserve row/header relationships better than plain hard splitting.
- [ ] PDF page metadata and Phase 1 lineage remain present after splitting.
- [ ] Incremental rebuild reuse remains protected when chunker config changes.
- [ ] Existing product-manual evals do not regress against the stored baseline, or any intentional trade-off is documented.
- [ ] Direction Gates 0, 1, and 2 are recorded in `implement.md`.

## Out of Scope

- Full `DocumentElement` / `DocumentAsset` storage.
- `/retrieve`, evidence builder, Agent context pack, or answer generation.
- PDF image extraction, page snapshots, OCR, visual embedding, or asset serving.
- Heavy PDF parsing dependency migration such as Marker/pdfplumber unless a later task explicitly chooses it.
- Learned chunking or embedding-based semantic boundary detection.
- Full Phase 2.5 indexing strategy implementation.
