# design.md - M8 Tag Suggestion UX

## Scope

M8 adds deterministic tag suggestions around the existing M5/M6/M7 manual metadata workflow. It should not make suggestions authoritative, persist metadata directly, or introduce a frontend build pipeline.

## Target Experience

```text
M7 upload/edit form
  -> operator fills metadata draft
  -> Suggest tags
  -> POST /manuals/tags/suggest
  -> render suggestion chips
  -> operator accepts one/all
  -> existing validate/save/upload flow persists metadata
```

## Technology Decision

### Chosen

- FastAPI JSON endpoint.
- Backend helper module, for example `src/tagmemorag/tag_suggestions.py`.
- Deterministic heuristics using existing metadata normalization helpers.
- Vanilla JavaScript additions to the M7 static file.

### Why

- The repo already has normalized tags and managed metadata sidecars.
- The UI is operational and should remain simple.
- Deterministic heuristics are testable, offline, and safe for local deployments.
- No external service or secret is needed for the MVP.

### Deferred

- LLM/embedding-powered semantic suggestions.
- Taxonomy registry.
- Bulk suggestion workflows.

## Proposed Files

```text
src/tagmemorag/
  tag_suggestions.py

src/tagmemorag/api.py
  POST /manuals/tags/suggest

src/tagmemorag/web/
  templates/manual_library.html
  static/manual_library.css
  static/manual_library.js

tests/unit/
  test_tag_suggestions.py
  test_tag_suggestions_api.py
  test_manual_library_ui.py
```

## API Contract

Request model:

```json
{
  "kb_name": "default",
  "metadata": {
    "manual_id": "cm1",
    "title": "CM1 Coffee Machine Maintenance Manual",
    "source_file": "coffee/cm1-maintenance.md",
    "product_category": "coffee",
    "product_model": "CM1",
    "tags": ["steam-wand"]
  },
  "text_sample": "optional bounded plain text sample",
  "limit": 8
}
```

Response model:

```json
{
  "kb_name": "default",
  "suggestions": [
    {
      "tag": "maintenance",
      "label": "maintenance",
      "score": 0.92,
      "sources": ["title", "source_file", "existing_tags"],
      "reason": "Matches title/source path and an existing KB tag."
    }
  ],
  "existing_tags": ["maintenance", "steam-wand"]
}
```

Notes:

- `tag` is normalized with `normalize_tag()`.
- `label` may match `tag` in M8; it exists so a future taxonomy can display friendlier names.
- `sources` are stable low-cardinality strings.
- `score` is deterministic and rounded for API readability.
- Invalid `limit` should map to `INVALID_INPUT` or Pydantic validation, consistent with nearby API behavior.

## Suggestion Algorithm

Inputs:

- Draft metadata fields.
- Optional bounded `text_sample`.
- Existing library records from `list_records(kb_name, settings, graph_state=...)`.
- Graph-derived facets from loaded KB state when available.

Candidate generation:

- Split path/title/category/brand/product/model/version/notes/sample into normalized tokens.
- Generate phrase candidates from path stems and title words where useful, for example `steam-wand`.
- Add exact existing KB tags as high-priority candidates when they appear in normalized draft text or share strong token overlap.
- Add category/model-derived candidates with moderate priority.

Scoring sketch:

```text
base score by source:
  existing_tags exact match: +0.60
  source_file/path:          +0.25
  title:                     +0.25
  product_category:          +0.20
  product_model/name:        +0.15
  notes/text_sample:         +0.10

bonuses:
  appears in multiple sources: +0.05 each
  used by multiple records:    +0.02 each capped

penalties/exclusions:
  already in draft tags: exclude
  stop words/extensions: exclude
  one-character tokens: exclude
  pure version strings: exclude unless part of model phrase
```

The exact weights can be tuned in implementation, but tests should assert ordering for representative cases rather than every numeric constant.

## Data Flow

Read flow:

```text
API request -> suggestion request model
  -> ensure_kb_access
  -> load existing managed records and optional graph facets
  -> tag_suggestions.suggest_tags(...)
  -> JSON response
```

UI flow:

```text
form fields -> metadata draft object -> API
  -> suggestion chips -> tags textarea mutation
  -> existing validation -> upload/save
```

Persistence flow:

- No persistence happens in the suggestion endpoint.
- Accepted suggestions only mutate local form state.
- Existing `POST /manuals` and `PATCH /manuals/{manual_id}/metadata` remain the only write paths.

## Auth and Privacy

- Use `require_scope("search")`, KB allowlist, and `rate_limit_dep`.
- Do not log raw `text_sample`, full notes, file content, or tokens.
- Keep `text_sample` bounded by request model validation or helper truncation.
- Do not store suggestion request payloads.

## UI Design

Add one suggestion block near each tags textarea:

- Button: `Suggest tags`
- Loading text in the same messages area or a small inline region.
- Suggestion chips:
  - chip text is the normalized tag
  - click chip to append it to tags
  - optional tiny reason text below/tooltip if practical
- Button: `Accept all`
- Empty state: `No new tag suggestions.`

Do not use a large assistant/chat-like surface. This remains an admin form control.

## Compatibility

- Existing `POST /manuals/validate`, upload, patch, list, rebuild, and search contracts remain unchanged.
- Existing sidecar metadata schema remains unchanged because tags are still stored in the existing `tags` field.
- Existing M7 page should keep working if suggestion API returns an error; form editing must remain available.

## Rollout / Rollback

Rollout:

- Ship endpoint and UI controls together.
- Document deterministic heuristic behavior in README.

Rollback:

- Hide/remove UI controls and route without affecting existing manual library APIs.
- No migration is required because no new persisted fields are introduced.

## Open Design Notes

- Decide during implementation whether `text_sample` is included from uploaded files. The MVP can omit browser file reading and still provide useful suggestions from metadata/path/title.
- Consider adding a config section later if stop words or scoring weights become operator-specific.

