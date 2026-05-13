# design.md - M14 Incremental Rebuild Strategy and Impact Reporting

## Scope

M14 builds on the M13 incremental managed-library rebuild path. It should improve reuse granularity, make `auto` mode policy-driven, and expose operational reports. It should not alter search ranking or introduce a database.

## Proposed Artifacts

Add durable files under `data/{kb}/`:

```text
chunk_identity.json
rebuild_impact.json
```

Rationale:

- `data/{kb}/` already represents built artifacts tied to a successful graph state.
- Failed rebuilds should not replace these files.
- The managed library manifest remains source working state; built identity belongs with the graph/vector artifacts it describes.

## Chunk Identity Contract

Recommended schema:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "build_id": "202605...",
  "parser": {"max_chars": 500, "min_chars": 50},
  "chunks": {
    "sha256:...": {
      "manual_id": "cm1",
      "source_file": "coffee/cm1.md",
      "path": ["Use"],
      "header": "Use",
      "start_line": 1,
      "text_hash": "sha256:...",
      "node_id": 0,
      "vector_row": 0,
      "metadata_hash": "sha256:..."
    }
  }
}
```

Identity key should prioritize stable semantic identity:

- `manual_id`
- normalized `source_file`
- normalized header/path
- text hash

`start_line` may be stored for diagnostics and tie-breaking, but it should not be the only identity because parser changes or edits can shift lines.

## Incremental Reuse Flow

```text
dirty manifest + old GraphState + chunk_identity.json
  -> parse dirty active manuals
  -> compute chunk identities for dirty chunks
  -> reuse vector rows for matching old identities
  -> embed only new/changed dirty chunks
  -> reuse unchanged non-dirty manual chunks as in M13
  -> rebuild final graph globally
  -> save full graph/vector artifacts + new identity map + impact report
```

Fallback reasons should be explicit:

- `missing_chunk_identity`
- `chunk_identity_schema_mismatch`
- `chunk_identity_build_mismatch`
- `ambiguous_chunk_identity`
- `parser_config_changed`
- `auto_threshold_exceeded`
- existing M13 reasons such as `missing_old_state` and `missing_dirty_state`

## Auto Mode Policy

Add config under managed manual library settings or rebuild settings:

```yaml
manual_library:
  incremental_auto_max_dirty_manuals: 20
  incremental_auto_max_dirty_chunks: 500
```

Decision order:

1. If no dirty state and pending changes exist: full with reason `missing_dirty_state`.
2. If dirty manual count exceeds threshold: full with `auto_dirty_manual_threshold_exceeded`.
3. Estimate dirty chunks by parsing metadata/list records or by previous identity map when available.
4. If dirty chunk estimate exceeds threshold: full with `auto_dirty_chunk_threshold_exceeded`.
5. Otherwise attempt incremental with fallback allowed unless request sets strict behavior.

## Impact Report Shape

Task response may include summary fields directly and a compact `impact_report` object:

```json
{
  "summary": {
    "manuals_added": 1,
    "manuals_removed": 0,
    "manuals_changed": 2,
    "chunks_added": 5,
    "chunks_removed": 3,
    "chunks_changed": 4,
    "chunks_reused": 120,
    "chunks_embedded": 6
  },
  "manuals": [
    {
      "manual_id": "cm1",
      "operation": "metadata_update",
      "outcome": "changed",
      "chunks_added": 0,
      "chunks_removed": 0,
      "chunks_reused": 12,
      "chunks_embedded": 0
    }
  ]
}
```

Do not include raw chunk text. For diagnostics, use hashes and counts.

## API / CLI

Recommended API:

```text
GET /manual-library/dirty?kb_name=default&format=json
GET /manual-library/dirty?kb_name=default&format=csv
GET /rebuild/{task_id}
```

`GET /rebuild/{task_id}` continues returning task metadata; it can include an impact summary or report artifact path.

Recommended CLI:

```bash
python -m tagmemorag manual-library dirty --kb default --format json
python -m tagmemorag manual-library dirty --kb default --format csv
python -m tagmemorag manual-library rebuild --kb default --mode auto
```

## Rollout / Rollback

- Identity map is additive. If absent or invalid, M13 behavior remains valid.
- Auto mode can ship while API/CLI defaults stay `full`.
- Impact report is operational metadata; search behavior does not depend on it.
- If chunk-level reuse is risky, keep impact report and auto threshold while falling back to M13 manual-level reuse.
