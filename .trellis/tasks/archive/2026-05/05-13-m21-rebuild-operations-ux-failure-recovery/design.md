# design.md - M21 Rebuild Operations UX and Failure Recovery

## Scope

M21 improves operator-facing rebuild status and recovery workflows for managed-library rebuilds. It should reuse the current in-memory task registry, manual-library manifest, rebuild impact artifact, and Qdrant sync summary rather than adding persistence or orchestration infrastructure.

The main design goal is a consistent status vocabulary across API, CLI, and docs.

## Current Flow

```text
manual mutation
  -> manifest.pending_changes = true
  -> manifest.dirty_manuals records operation

manual-library rebuild
  -> start_library_rebuild()
  -> AppState.start_rebuild()
  -> _build_for_rebuild()
       -> full / incremental / auto decision
       -> task detail fields updated
  -> if Qdrant library rebuild: sync_qdrant_for_rebuild()
  -> save artifacts
  -> graph swap
  -> clear_pending_after_success()
```

Important safety property: dirty state clears through the `on_success` callback only after save/swap succeeds. Failed rebuilds leave the old graph active and pending changes intact.

## Proposed User Flow

```text
operator sees rebuild failure
  -> inspect task/status summary
  -> inspect pending library state
  -> choose recovery:
       retry incremental
       force full rebuild
       inspect dirty CSV
       switch provider to npz
  -> rerun rebuild
  -> verify pending_changes=false and impact/qdrant summary
```

## Data Contracts

### Rebuild Operations Summary

Add a small summary object, either as a helper output inside existing task payloads or as fields on inspection responses:

```json
{
  "status": "failed",
  "requested_mode": "incremental",
  "effective_mode": "incremental",
  "dirty_manual_count": 1,
  "fallback_reason": "",
  "chunk_identity_fallback_reason": "",
  "qdrant_sync": {
    "provider": "qdrant",
    "strategy": "point_incremental",
    "points_upserted": 1,
    "points_deleted": 0,
    "points_reused": 1,
    "fallback_reason": ""
  },
  "current_build_id": "20260513203000000000",
  "last_successful_build_id": "20260513203000000000",
  "pending_changes": true,
  "recovery_hint": "retry_incremental"
}
```

Recommended recovery hint values:

- `none`
- `inspect_dirty`
- `retry_incremental`
- `force_full_rebuild`
- `check_qdrant_then_retry`
- `switch_to_npz_or_restore_qdrant`

These hints should be derived from low-cardinality task/manifest/config state, not exception messages.

### Pending State Inspection

Prefer extending current dirty state output:

```json
{
  "kb_name": "default",
  "pending_changes": true,
  "dirty_manual_count": 1,
  "dirty_manuals": [],
  "current_build_id": "...",
  "last_impact_summary": {},
  "last_qdrant_sync": {},
  "recovery_actions": ["retry_incremental", "force_full_rebuild"]
}
```

CSV compatibility should keep existing columns first. If new CSV columns are needed, append them rather than reordering existing fields.

## API Design

MVP options:

1. Extend `GET /manual-library/dirty` JSON response with pending/build/recovery fields while preserving `dirty_manuals`.
2. Add `GET /manual-library/rebuild-status?kb_name=default` if dirty export should remain narrow.

Recommendation: extend `GET /manual-library/dirty` for M21 because it is already the operator inspection endpoint and the CLI command mirrors it.

`GET /rebuild/{task_id}` can include the same summary object for live or recently completed tasks. Since the task registry is process-local, document that this endpoint is for current-process task inspection only.

## CLI Design

MVP options:

1. Extend `python -m tagmemorag manual-library dirty --format json` to include pending/build/recovery fields.
2. Add `python -m tagmemorag manual-library status --kb default` as a higher-level operator command.

Recommendation: add `manual-library status` only if the dirty JSON becomes too broad. Otherwise extend `dirty` and improve `manual-library rebuild` failure output.

CLI rebuild output should remain JSON by default for machine readability. Optional human formatting can be deferred unless already present in local CLI patterns.

## Qdrant Recovery Safety

Existing `sync_qdrant_for_rebuild()` ordering is the safety boundary:

1. upsert new/changed points
2. refresh reused payloads
3. delete stale ids

M21 tests should preserve the guarantee that a failure before stale delete leaves old graph active, dirty state pending, and stale point deletion unattempted.

Full rebuild recovery should be tested after a failed incremental payload refresh or simulated Qdrant sync failure. The recovery test should use `FakeQdrantClient` and assert a later full rebuild succeeds and clears pending state.

## Compatibility

- Existing task payload fields remain.
- Existing `manual-library dirty` JSON keeps `kb_name`, `dirty_manual_count`, and `dirty_manuals`.
- Existing CSV columns remain in order.
- No new production dependency is needed.

## Observability And Safety

Safe fields:

- counts
- enum-like strategy/reason strings
- build ids
- KB names
- manual ids/source files already present in operator dirty-state output

Unsafe fields:

- raw chunk text
- vectors
- raw Qdrant payload dumps
- candidate id lists
- secrets or credentials
- full exception traces in normal API output

## Rollout / Rollback

Rollout is low risk because fields are additive and focused on operator surfaces.

Rollback can remove additive summary fields and docs without changing rebuild core semantics. Do not change dirty-state clearing or Qdrant sync ordering unless tests prove the replacement preserves the same guarantees.

## Open Questions

- Should M21 add a distinct `manual-library status` CLI/API surface, or extend `dirty` only?
  - Recommendation: extend `dirty` first; add `status` only if the response becomes confusing.
- Should recovery hints be exposed as a single `recovery_hint` or a list of `recovery_actions`?
  - Recommendation: list actions on inspection responses, single primary hint on task failure summaries.
