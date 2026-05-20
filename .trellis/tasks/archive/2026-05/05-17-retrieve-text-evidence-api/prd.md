# Phase 3: Retrieve Text Evidence API

## Goal

Add the first Agent-facing `/retrieve` API that returns text-only evidence, citations, raw hits, and a compact context pack. It should reuse the existing search stack and lineage metadata while keeping `/search` backward-compatible.

This is the first runtime step after Phase 2.5. It should not implement visual evidence, assets, OCR, multimodal retrieval, or `/answer`.

## Requirements

- Add `POST /retrieve`.
- Request shape should be compatible with `SearchRequest` and add optional `token_budget`.
- Response must include:
  - `schema_version`;
  - `build_id`;
  - `kb_name`;
  - `trace_id`;
  - `search_id` or `retrieve_id`;
  - raw `results`;
  - text `evidence`;
  - `citations`;
  - `context_pack`;
  - `answerability`;
  - optional safe `debug`.
- Evidence should include:
  - request-scoped `evidence_id`;
  - request-scoped `citation_id`;
  - matched `chunk_id`;
  - `doc_id`;
  - `source_file`;
  - `page_range` when available;
  - `section_path`;
  - text snippet;
  - score/confidence;
  - reason.
- Context pack should:
  - respect a simple token/character budget;
  - include selected context items with citations/evidence refs;
  - keep retrieved text separate from instructions.
- Insufficient evidence signaling should expose:
  - answerability;
  - confidence;
  - warnings;
  - fallback reason.
- Keep `/search` unchanged.

## Acceptance Criteria

- [ ] `/retrieve` returns text evidence and context pack for a loaded KB.
- [ ] Evidence and context items reference stable lineage metadata (`doc_id`, `chunk_id`) when present.
- [ ] No-result retrieval returns explicit insufficient-evidence signaling.
- [ ] `/search` response shape remains compatible.
- [ ] Tests cover response shape, citations, context budget, no-answer behavior, and permissions.
- [ ] Full tests and eval CI pass.

## Out of Scope

- Visual evidence, page snapshots, crops, assets, OCR, or image vectors.
- `/answer` or LLM generation.
- Learned fusion or ranking changes.
- Parent chunk expansion.
- Qdrant point id migration.
