# M8 Tag Suggestion UX

## Goal

Add a lightweight tag suggestion workflow to the managed manual library so operators can quickly create consistent, search-useful tags during upload and metadata editing. Suggestions should reduce manual typing and tag drift without taking control away from the operator or changing the canonical metadata validation rules.

## Background / Known Context

- M5 introduced normalized manual metadata tags and tag-aware retrieval boosts.
- `normalize_tag()` already lowercases tags and converts whitespace/underscores/non-alphanumeric runs into stable dash-separated tags.
- M6 introduced the managed manual library API and stores manual metadata in sidecar JSON files.
- M7 introduced `/admin/manual-library`, including upload/edit forms where tags are entered as comma/newline-separated text.
- Current operators must invent tags manually. Similar concepts can drift into variants such as `maintenance`, `maintain`, `cleaning`, and `clean`.
- Existing JSON APIs remain canonical. M8 should add suggestion help around them, not replace validation or storage behavior.

## Product Direction

M8 should feel like a quiet assistive layer inside the M7 operations UI:

- Suggestions are optional and reviewable.
- The UI should explain why a tag was suggested when space allows.
- Operators can accept individual suggestions, accept all, or ignore them.
- Suggestions should prefer consistency with tags already used in the selected KB.
- The backend should be deterministic and safe by default, with no external LLM dependency for the MVP.

## Requirements

### 1. Suggestion API

- Add a backend API endpoint for tag suggestions, recommended route: `POST /manuals/tags/suggest`.
- Request should include:
  - `kb_name`, default `default`
  - draft metadata fields such as `manual_id`, title, source file, brand, product category, product name, product model, language, version, notes, and existing tags
  - optional text sample or source filename signal for upload flows
  - optional `limit`, default small such as 8
- Response should include:
  - `kb_name`
  - `suggestions`, ordered by score descending
  - each suggestion with normalized `tag`, display `label`, `score`, `sources`, and short `reason`
  - `existing_tags` or facets used for consistency when useful
- The endpoint should use existing auth behavior:
  - require `search` scope for read-only suggestions
  - enforce KB allowlist with `ensure_kb_access`
  - apply existing rate limiting
- Errors should keep the standard `{code, message, detail}` shape.

### 2. Deterministic Suggestion Engine

- Add a small backend suggestion module rather than embedding logic in `api.py`.
- Generate candidates from:
  - normalized tokens in source path / filename
  - title
  - product category
  - brand / product name / product model
  - notes
  - existing tags in the KB manual library
  - existing graph-derived manual facets when a KB is loaded
- Prefer existing KB tags when candidate text is similar or identical after normalization.
- Exclude tags already present in the draft metadata.
- Exclude low-value generic tokens such as file extensions, stop words, version-only tokens, and very short tokens unless they are part of a meaningful model string.
- Cap suggestions and keep scoring deterministic.
- Do not read full manual file content from disk in the MVP. For upload, the browser may send a bounded text sample if easy, but the endpoint must work without it.

### 3. Admin UI Integration

- Add suggestion controls to the M7 upload form and detail/edit panel near the tags field.
- Provide a `Suggest tags` action for upload and edit flows.
- Render suggestions as compact chips/buttons.
- Allow accepting:
  - one suggestion at a time
  - all currently suggested tags
- Do not auto-save accepted suggestions. They should update the form field only; existing validate/save/upload actions remain the commit step.
- Show loading and error states inline without blocking unrelated form editing.
- Preserve token/sessionStorage behavior from M7.

### 4. Validation and Normalization Flow

- Suggestions returned by the API should already be normalized.
- The UI should still call `POST /manuals/validate` before upload/save.
- If the operator accepts suggestions and validation further normalizes them, validation output remains the source of truth.
- Duplicate accepted tags should be removed client-side for ergonomics and server-side for safety if helper code exists.

### 5. Documentation

- Update README to describe the suggestion endpoint and UI action.
- Document that suggestions are deterministic heuristics in M8, not LLM-generated authoritative taxonomy.
- Document that suggestions do not change persisted metadata until upload/save succeeds.

## Acceptance Criteria

- [ ] `POST /manuals/tags/suggest` returns normalized, scored tag suggestions for a draft manual metadata payload.
- [ ] Suggestions use filename/path/title/category/model and existing KB tags when available.
- [ ] Existing tags in the request are not suggested again.
- [ ] The endpoint enforces auth scope, KB allowlist, rate limiting, and structured error responses.
- [ ] Upload UI can request suggestions and accept one/all suggestions into the tags field.
- [ ] Detail/edit UI can request suggestions for an existing manual draft and accept one/all suggestions into the tags field.
- [ ] Accepted suggestions are not persisted until the operator uploads or saves metadata.
- [ ] Validation remains required before upload/save and still provides canonical normalized metadata.
- [ ] Tests cover suggestion helper scoring/deduping and API behavior.
- [ ] Tests cover static/template/UI wiring at an appropriate level.
- [ ] Existing M5/M6/M7 behavior and JSON API tests remain compatible.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Suggestion API and deterministic backend helper are implemented.
- M7 admin UI exposes suggestion controls in upload and edit flows.
- README documents API and UI usage.
- Focused tests for tag suggestions and admin UI pass.
- `uv run pytest tests/ -q` passes.
- Browser or HTTP-level smoke confirms `/admin/manual-library` still loads.

## Out of Scope

- External LLM-powered tag generation.
- Product taxonomy management or canonical tag hierarchy.
- Bulk tagging across many manuals.
- Automatic metadata save/upload after accepting suggestions.
- Full manual-content NLP over large files.
- Multilingual segmentation beyond simple deterministic tokenization.
- DB-backed tag registry or audit timeline.

## Follow-Up Ideas

- Optional LLM provider for richer suggestions behind config and explicit operator review.
- Tag synonym management and canonical taxonomy.
- Bulk tag suggestion/review queue.
- Query classifier that uses accepted tags/category/model to route likely search filters.
- Analytics for unused/duplicate tags.

