# design.md - M11 Tag Governance, Synonyms, and Drift Analytics

## Scope

M11 adds a file-backed tag governance layer on top of the existing manual metadata and managed manual library. It should not replace `ManualMetadata.tags` or the current no-policy behavior. The shared backend service should power API, admin UI, and CLI flows so policy resolution, stats, drift detection, and merge/rename behavior remain consistent.

## Current State

```text
manual sidecar tags
  -> ManualMetadata.from_dict() normalizes tags
  -> build_kb() stores tags on graph nodes
  -> /manuals returns graph-derived facets
  -> /manuals/tags/suggest uses records + graph facets
  -> /manual-library lists managed records
  -> M10 bulk preview/import validates row tags but has no taxonomy policy
```

Important existing files:

- `src/tagmemorag/manuals.py`: `normalize_tag()`, `ManualMetadata`, sidecar shape.
- `src/tagmemorag/manual_library.py`: safe library root, records, sidecar writes, pending marker.
- `src/tagmemorag/tag_suggestions.py`: deterministic tag suggestion engine.
- `src/tagmemorag/wave_searcher.py`: tag filter normalization and tag boost.
- `src/tagmemorag/manual_bulk_import.py`: batch preview/import validation.
- `src/tagmemorag/api.py`: manual/library/search/admin endpoints.
- `src/tagmemorag/web/templates/manual_library.html` and `src/tagmemorag/web/static/manual_library.js/css`: admin UI.

## Target Flow

```text
.tagmemorag-tags.json
  -> load/validate policy
  -> resolve raw tags to canonical tags
  -> stats + drift report
  -> validation/suggestion/search warnings or canonicalization
  -> preview merge/rename
  -> commit sidecar rewrites + optional policy update
  -> mark pending rebuild
```

The product boundary is preview-first: operators should see counts and affected manuals before any sidecar or policy file is changed.

## Proposed Module Boundary

Add `src/tagmemorag/tag_governance.py`.

Responsibilities:

- Load and save per-KB tag policy.
- Validate policy shape, canonical tags, synonyms, deprecated tags, and cycle-free resolution.
- Resolve raw tags to canonical tags.
- Compute tag usage stats from managed records and optionally loaded graph state.
- Detect drift issues.
- Build merge/rename previews.
- Commit merge/rename changes by calling existing manual library sidecar write/update paths where practical.

Keep this module independent of FastAPI request objects, browser UI state, and CLI argument parsing.

## File Contract

Store policy at:

```text
{manual_library.root_dir}/{kb_name}/.tagmemorag-tags.json
```

Recommended schema:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "policy_mode": "advisory",
  "canonical_tags": [
    {
      "tag": "maintenance",
      "label": "Maintenance",
      "description": "Cleaning, upkeep, and routine care"
    }
  ],
  "synonyms": {
    "cleaning": "maintenance",
    "clean": "maintenance"
  },
  "deprecated_tags": {
    "maintainance": {
      "replacement": "maintenance",
      "reason": "Misspelling"
    }
  },
  "updated_at": "2026-05-13T00:00:00+00:00"
}
```

`policy_mode`:

- `advisory`: unknown/deprecated/synonym tags become validation warnings.
- `strict`: unknown/deprecated tags become validation errors; synonyms remain warnings with canonical replacement.

MVP can keep `canonical_tags` as list objects and normalize every `tag` field on load. Unknown policy fields should be ignored or reported as warnings only if needed; the policy file is owned by operators, not end users.

## Data Contracts

### TagPolicy

Recommended dataclasses:

```python
@dataclass(frozen=True)
class CanonicalTag:
    tag: str
    label: str = ""
    description: str = ""

@dataclass(frozen=True)
class DeprecatedTag:
    tag: str
    replacement: str = ""
    reason: str = ""

@dataclass(frozen=True)
class TagPolicy:
    kb_name: str
    schema_version: str = "1"
    policy_mode: Literal["advisory", "strict"] = "advisory"
    canonical_tags: tuple[CanonicalTag, ...] = ()
    synonyms: Mapping[str, str] = field(default_factory=dict)
    deprecated_tags: tuple[DeprecatedTag, ...] = ()
    updated_at: str = ""
```

### TagUsageStat

```python
@dataclass(frozen=True)
class TagUsageStat:
    tag: str
    canonical_tag: str
    state: Literal["canonical", "synonym", "deprecated", "unknown"]
    manual_count: int
    active_manual_count: int
    inactive_manual_count: int
    graph_count: int
    examples: tuple[str, ...]
```

### TagDriftIssue

```python
@dataclass(frozen=True)
class TagDriftIssue:
    code: str
    severity: Literal["info", "warning", "error"]
    tag: str
    canonical_tag: str
    count: int
    manual_ids: tuple[str, ...]
    message: str
```

### TagRewritePreview / Result

```python
@dataclass(frozen=True)
class TagRewriteChange:
    manual_id: str
    source_file: str
    before_tags: tuple[str, ...]
    after_tags: tuple[str, ...]

@dataclass(frozen=True)
class TagRewritePreview:
    kb_name: str
    mode: Literal["merge", "rename"]
    source_tags: tuple[str, ...]
    target_tag: str
    affected_count: int
    changes: tuple[TagRewriteChange, ...]
    issues: tuple[TagDriftIssue, ...]
```

## Resolution Rules

1. Normalize every input tag with `normalize_tag()`.
2. If tag is canonical, resolution is itself.
3. If tag is a synonym, recursively resolve target.
4. If tag is deprecated and has replacement, resolve to replacement for suggestions/search, but validation should still report deprecated usage.
5. If no policy file or no canonical tags are configured, unknown tags remain valid and resolve to themselves.
6. If policy has canonical tags and a tag is not canonical/synonym/deprecated, classify as `unknown`.
7. Detect cycles such as `a -> b -> a` during load and reject the policy.

## Stats and Drift Detection

Inputs:

- Managed records from `list_records(kb_name, settings)`.
- Optional graph state from `app_state.kbs.get(kb_name)`.
- Current tag policy.

Stats should count each tag once per manual. If a manual has duplicate tags after normalization, dedupe for counts.

Drift issue examples:

- `UNKNOWN_TAG`: tag is outside configured canonical/synonym/deprecated sets.
- `SYNONYM_IN_USE`: sidecar uses a synonym instead of canonical tag.
- `DEPRECATED_TAG_IN_USE`: sidecar still uses a deprecated tag.
- `LIKELY_DUPLICATE_TAG`: simple deterministic near-match to a canonical tag.
- `GRAPH_LIBRARY_TAG_DRIFT`: loaded graph tag set differs from current sidecars, usually requiring rebuild.

For typo detection, MVP should be conservative:

- exact normalized prefix/suffix relation with edit distance <= 2 for tags length >= 5, or
- token-set overlap >= 0.8 with different order.

Avoid heavy fuzzy-matching dependencies unless a clear need emerges.

## Validation Integration

Add optional governance checks to existing validation flows:

- `manual_library.validate_metadata()` can optionally accept a policy or a governance result, or API layer can post-process `MetadataValidationResult`.
- M10 `manual_bulk_import.preview_bulk_import()` should surface governance messages per row.
- Keep no-policy behavior unchanged.

Validation message codes:

- `TAG_SYNONYM_USED`
- `TAG_DEPRECATED`
- `TAG_UNKNOWN`
- `TAG_POLICY_INVALID`

Severity mapping:

- advisory: synonym/deprecated/unknown are warnings.
- strict: unknown/deprecated are errors; synonym is warning unless configured otherwise.

## Suggestion Integration

Update `tag_suggestions.suggest_tags()` to accept optional `TagPolicy`.

- Candidate tags are resolved to canonical tags before scoring.
- Suggestions should not return deprecated tags.
- If draft metadata includes synonyms, suggest the canonical replacement.
- Existing tags from library/graph should be counted by canonical tag when policy exists.
- Reason text should mention policy/synonym matches without exposing large raw lists.

## Search Filter Integration

Search filters already normalize tags in `wave_searcher.normalize_filters()`.

Options:

1. API-layer resolution: resolve `SearchFilters.tags` before calling `wave_search()`.
2. Search-layer resolution: pass policy into `normalize_filters()`.

Recommended MVP: API-layer resolution for HTTP search and CLI-layer resolution for CLI search. This keeps `wave_searcher.py` mostly algorithmic and avoids importing manual library policy into the search core.

Important compatibility note: graph nodes still contain sidecar tags until rebuild. If sidecars are rewritten to canonical tags but graph is stale, synonym resolution can only help filters that match graph tags already present. UI should show rebuild drift.

## Merge / Rename Semantics

`merge`:

- Replace every source tag with target tag.
- If a manual already has target tag, remove the source tag and keep one target.
- Optional policy update: source tags become synonyms of target.

`rename`:

- Intended for one source tag -> one target tag.
- Same sidecar rewrite mechanics as merge.
- Optional policy update: source tag becomes deprecated with replacement target, or synonym depending on request.

Commit flow:

1. Build preview.
2. Reject if preview has blocking issues.
3. For each affected record:
   - merge tags in memory.
   - call existing metadata update path or a shared metadata sidecar writer.
4. Mark pending after successful mutation.
5. Return imported/updated/skipped/failed counts and changed records.

If a filesystem write fails mid-operation, return a partial-failure report. Do not attempt a complex transaction log in M11 MVP; atomic per-sidecar writes plus explicit report is acceptable.

## API Design

### `GET /manual-library/tags`

Query:

- `kb_name`

Response:

```json
{
  "kb_name": "default",
  "policy": {...},
  "summary": {
    "tag_count": 12,
    "canonical_count": 7,
    "synonym_count": 3,
    "deprecated_count": 1,
    "unknown_count": 2,
    "drift_count": 4,
    "rebuild_required": true
  },
  "stats": [...],
  "issues": [...]
}
```

Requires `search` scope and KB access.

### `PUT /manual-library/tags/policy`

Body:

```json
{
  "kb_name": "default",
  "policy": {...}
}
```

Requires write/admin scope and KB access.

### `POST /manual-library/tags/rewrite/preview`

Body:

```json
{
  "kb_name": "default",
  "mode": "merge",
  "source_tags": ["cleaning", "clean"],
  "target_tag": "maintenance",
  "policy_update": "synonym"
}
```

Requires `search` scope and KB access.

### `POST /manual-library/tags/rewrite`

Same body as preview plus optional confirmation fields. Reruns preview internally.

Requires write/admin scope and KB access.

## Admin UI Design

Add a Tag Governance section or dialog to the existing manual library admin page.

Expected views:

- Facets table: tag, canonical tag, state, manual count, active count, graph count.
- Drift table: severity, code, tag, canonical/replacement, count, message.
- Policy editor: canonical tag list and synonym/deprecated mappings. MVP can use dense JSON textarea plus validation summary if a full table editor is too large.
- Rewrite form: source tags, target tag, mode, policy update option.
- Rewrite preview table: manual id, source file, before tags, after tags.

Keep controls explicit. Commit buttons should be disabled until a successful preview exists.

## CLI Design

Add subcommands under `manual-tags` or similar:

```bash
python -m tagmemorag manual-tags stats --kb default --config config.yaml
python -m tagmemorag manual-tags policy validate --kb default --config config.yaml --policy tags.json
python -m tagmemorag manual-tags rewrite-preview --kb default --source cleaning --source clean --target maintenance
python -m tagmemorag manual-tags rewrite --kb default --source cleaning --target maintenance --policy-update synonym
```

Prefer thin wrappers over `tag_governance.py`.

## Observability and Security

- Logs:
  - `tag_governance_stats`
  - `tag_governance_policy_update`
  - `tag_governance_rewrite`
- Safe fields only:
  - `kb_name`
  - operation
  - counts
  - result status
  - trace id
- Metrics, if added, must use bounded labels only. Do not label by raw tag.
- API errors use existing structured `ServiceError` shape.

## Testing Strategy

Unit tests:

- policy parse/write/load/missing-file
- synonym resolution and cycle detection
- stats from managed records and graph state
- drift issue detection
- rewrite preview and idempotent commit
- governance validation message severity
- suggestion canonicalization
- search filter synonym resolution

API tests:

- stats endpoint auth/read scope
- policy update write scope
- rewrite preview read scope
- rewrite commit write scope
- no-policy backward compatibility

UI tests:

- admin route includes tag governance controls.
- static JS references tag governance endpoints and render functions.

CLI tests:

- stats output JSON
- rewrite preview output JSON
- rewrite commit updates sidecars and marks pending.

## Rollout / Rollback

Rollout:

- Ship with no policy file by default, preserving existing behavior.
- Operators can add `.tagmemorag-tags.json` per KB gradually.
- Advisory mode should be the recommended first production mode.
- Strict mode should be opt-in after drift is cleaned up.

Rollback:

- Remove or rename `.tagmemorag-tags.json` to return to no-policy behavior.
- Existing sidecars remain valid because tags are still plain normalized strings.
- If a rewrite produces undesired sidecar changes, restore from VCS/backups or re-run inverse rewrite and rebuild.

## Open Design Risks

- Full transactionality across many sidecars is out of MVP scope; partial failures must be reported clearly.
- Search filter synonym resolution is limited by the currently loaded graph tags until rebuild.
- A powerful UI policy editor can grow large; MVP may start with JSON editor plus validation and focused rewrite controls.
