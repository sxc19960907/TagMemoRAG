# M11 Tag Governance, Synonyms, and Drift Analytics

## Goal

Turn tags from free-form metadata strings into governed KB-level retrieval assets. M11 adds tag usage statistics, canonical tag and synonym mapping, safe merge/rename operations, and an admin UI view that shows tag facets plus drift problems before they degrade filtering, suggestions, batch imports, or search quality.

## Background / Known Context

- M5 introduced `ManualMetadata.tags`, tag normalization, metadata facets, tag-aware retrieval filters, and tag result fields.
- M6 introduced the file-backed managed manual library under `manual_library.root_dir/{kb_name}` with safe sidecar writes and pending rebuild markers.
- M7 introduced `/admin/manual-library`, a dense operations UI on the M6 JSON APIs.
- M8 introduced deterministic tag suggestions using draft metadata, existing library tags, and loaded graph facets.
- M10 introduced batch JSON/JSONL/CSV import, preview rows that include tag/status/action/severity, and thin CLI helpers.
- Today, tags are normalized but not governed. Operators can accidentally create near-duplicates like `clean`, `cleaning`, `maintenance`, `maintainance`, and `清洁维护`; these tags then fragment UI facets, search filters, suggestions, and bulk-import review.
- Tag governance must remain file-backed for now, consistent with the managed manual library. A database registry and audit timeline can be follow-ups.

## Assumptions

- M11 stores governance policy per KB under the managed library root, recommended file: `.tagmemorag-tags.json`.
- Canonical tags use the existing `normalize_tag()` lower-kebab-case rule.
- Synonyms and aliases normalize through the same rule before lookup.
- Governance affects metadata validation, tag suggestion, bulk preview, admin UI, and search filters, but does not silently rewrite existing source sidecars unless an operator explicitly runs a merge/rename action.
- A mutating merge/rename marks the KB library as pending rebuild. The currently served graph remains unchanged until rebuild succeeds.
- Production safety matters more than convenience: destructive or broad changes need preview, explicit confirmation, and rollback-friendly file-backed behavior.

## Requirements

### 1. Tag Governance Policy

- Add a per-KB tag policy with:
  - `canonical_tags`: governed tags and optional display labels/descriptions.
  - `synonyms`: alias tag -> canonical tag mapping.
  - `deprecated_tags`: tags that should no longer be used and optional replacement tags.
  - `updated_at` and schema metadata.
- Policy load should tolerate a missing file by returning an empty policy.
- Policy write must be atomic and constrained to the KB manual library root.
- Invalid policy shape, synonym cycles, or synonym targets that do not resolve to canonical tags must return structured errors.

### 2. Tag Usage Statistics

- Provide tag usage stats per `kb_name`, including:
  - raw tag
  - canonical tag after policy resolution
  - synonym/deprecated/governed state
  - manual count
  - active manual count
  - disabled/archived manual count
  - graph/searchable count when a loaded graph exists
  - example `manual_id` values, capped to avoid large payloads
- Stats should distinguish managed-library state from the currently searchable graph so operators can see pending rebuild drift.
- API and UI summaries should be bounded and not expose raw document text.

### 3. Drift Detection

- Detect and report tag drift issues:
  - unknown tags not in `canonical_tags` when a policy is configured.
  - deprecated tags still present in sidecars.
  - synonym tags that should be replaced by canonical tags.
  - likely typo/near-duplicate tags where a simple deterministic heuristic is strong enough.
  - tags present in sidecars but not present in the loaded graph, and graph tags absent from current sidecars.
- Each drift issue should include severity, code, raw tag, canonical/replacement tag when known, count, and actionable message.

### 4. Merge / Rename Preview

- Add a non-mutating preview operation for tag merge/rename:
  - input: source tag(s), target canonical tag, mode (`merge` or `rename`), `kb_name`.
  - output: affected manuals, before/after tag sets, action counts, drift impact, and rebuild requirement.
- Preview must validate target tag safety and synonym/deprecated policy effects.
- Preview must not write sidecars or policy.

### 5. Merge / Rename Commit

- Add explicit commit operations for merge/rename:
  - update affected sidecar metadata tags atomically.
  - optionally update governance policy so source tags become synonyms or deprecated aliases of the target.
  - mark the manual library pending rebuild after successful writes.
  - report partial failures if a sidecar write fails mid-batch.
- Re-running the same operation should be idempotent: no duplicate tags and no needless sidecar churn.
- Commit must require write/admin scope and KB allowlist access.

### 6. Governance-Aware Validation and Suggestions

- Extend `POST /manuals/validate` and bulk preview/import validation to surface governance warnings/errors:
  - synonym tag used -> warning with canonical replacement.
  - deprecated tag used -> warning or error according to policy/default.
  - unknown tag under strict policy -> warning or error according to request or policy mode.
- Extend tag suggestions to prefer canonical tags and explain when a suggestion comes from a synonym or policy match.
- Search filters should accept synonyms and resolve them to canonical tags before filtering where possible.

### 7. Admin UI Integration

- Extend `/admin/manual-library` with a Tag Governance workspace:
  - tag facets table with counts and canonical state.
  - drift issue list with filters by severity/code/status/canonical tag.
  - policy editor for canonical tags and synonyms.
  - merge/rename preview table.
  - explicit commit controls for safe tag rewrites.
- Keep the existing operations-console style: dense, scannable, conservative around broad changes.
- Show pending rebuild state after a successful mutation.

### 8. CLI and Documentation

- Add thin CLI helpers over the same backend/service behavior:
  - tag stats
  - tag drift preview
  - tag merge/rename preview
  - tag merge/rename commit
- Update README and `product_manuals/README.md` with:
  - `.tagmemorag-tags.json` template.
  - synonym/canonical examples.
  - merge/rename workflow.
  - drift meaning and resolution guidance.

### 9. Auth, Observability, and Safety

- Require KB access for all tag governance operations.
- Require read/search scope for stats and drift preview.
- Require rebuild/admin-equivalent write scope for mutating merge/rename and policy update.
- Log only low-cardinality safe fields: `kb_name`, operation, counts, result status, and trace id.
- Do not log raw manual text, full sidecar content, API keys, or raw high-cardinality tag values in metrics labels.
- Preserve existing `/search`, `/manuals`, `/manuals/tags/suggest`, `/manual-library`, bulk import, and rebuild behavior for deployments without a tag policy file.

## Acceptance Criteria

- [ ] Operators can fetch tag usage stats for a KB and see raw tag, canonical tag, usage counts, governed state, and searchable-vs-library drift.
- [ ] Operators can define canonical tags, synonyms, and deprecated tags in a file-backed KB policy.
- [ ] Governance policy load/write is atomic, safe under the manual library root, and validates cycles and invalid targets.
- [ ] Manual validation and bulk preview report actionable tag governance warnings/errors without silently mutating metadata.
- [ ] Tag suggestions prefer canonical tags and indicate policy/synonym reasons.
- [ ] Search tag filters accept synonyms and resolve to canonical tags where policy allows.
- [ ] Operators can preview merge/rename impact before sidecars change.
- [ ] Merge/rename commit updates affected sidecars safely, dedupes tags, marks pending rebuild, and returns a clear result report.
- [ ] Admin UI shows tag facets, drift issues, policy state, merge/rename preview, and explicit commit controls.
- [ ] Existing no-policy behavior remains backward compatible.
- [ ] Tests cover policy parsing/validation, usage stats, drift detection, validation integration, suggestion/search resolution, merge/rename preview and commit, API auth, CLI helpers, and UI route/static behavior.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Unit and API tests cover tag policy, stats, drift, merge/rename, validation, suggestions, search filter resolution, and commit behavior.
- UI route/static tests cover the tag governance controls at an appropriate level.
- Documentation includes policy templates and production workflow guidance.
- `uv run pytest tests/ -q` passes.
- Any durable backend conventions learned during implementation are added to `.trellis/spec/backend/`.

## Out of Scope

- Database-backed taxonomy registry.
- Durable audit timeline or approval workflow.
- Multi-user collaborative governance review.
- LLM-based semantic tag clustering.
- Automatic OCR or document text classification.
- Cross-KB global taxonomy enforcement.
- Automatic rebuild by default after tag rewrite.
- Prometheus metrics labeled by raw tag values.

## Follow-Up Ideas

- Saved governance change requests with approval state.
- CSV export of drift issues.
- Cross-KB taxonomy sharing with per-KB overrides.
- Tag usage time series and trend dashboards.
- LLM-assisted synonym suggestions reviewed by operators.
- Bulk category/product taxonomy governance using the same policy engine.
