# M21 Rebuild Operations UX and Failure Recovery

## Goal

Make managed-library rebuild state easier to inspect, explain, and recover from after failures, especially when incremental rebuilds and Qdrant point-level sync are involved.

M21 should turn the existing rebuild task registry, dirty manifest, impact report, API, CLI, and admin UI signals into a coherent operator workflow: what changed, what rebuild tried to do, why it failed or fell back, whether dirty changes remain pending, and which recovery action is safe.

## Background / Known Context

- Managed-library rebuilds already support `mode=full`, `mode=incremental`, and `mode=auto`.
- Rebuild tasks already expose fields such as `requested_mode`, `effective_mode`, `dirty_manual_count`, `fallback_reason`, `reused_chunk_count`, `embedded_chunk_count`, `auto_decision_reason`, `chunk_identity_fallback_reason`, `impact_summary`, and `qdrant_sync`.
- `GET /rebuild/{task_id}` returns in-memory task status, but completed task history is process-local and disappears after restart.
- `GET /manual-library` returns pending state and dirty manuals. `GET /manual-library/dirty` and `python -m tagmemorag manual-library dirty` export dirty state as JSON or CSV.
- Qdrant-backed managed-library rebuilds already sync before graph/meta swap. Failed Qdrant sync keeps the old loaded graph active and should leave dirty state pending.
- Existing tests cover failed library rebuild pending markers, Qdrant full sync stale deletes, point-level incremental sync, payload refresh for reused points, and failure ordering when payload refresh fails before stale delete.
- M20 expanded eval coverage and should remain available as an optional measurement tool after rebuild recovery scenarios.

## Requirements

### 1. Operator-Facing Rebuild Status Summary

- Add or refine a concise rebuild status summary that can be returned by API and CLI without requiring operators to infer state from several low-level fields.
- Include only low-cardinality, safe fields:
  - task id and status
  - requested mode and effective mode
  - fallback reason and auto decision reason
  - dirty manual count
  - reused and embedded chunk counts
  - chunk identity fallback reason
  - qdrant sync strategy/counts/fallback reason when present
  - current or last successful build id when available
  - whether pending library changes remain after task completion or failure
- Keep existing task response fields backward compatible. New fields should be additive or grouped under an additive object.

### 2. Pending State Inspection

- Add a focused inspection command and/or API response that answers:
  - are there pending library changes?
  - which manuals are dirty and why?
  - is each dirty manual still present/searchable?
  - what is the current loaded build id?
  - what was the last rebuild impact summary if available?
  - what safe recovery actions are available?
- Prefer extending existing `manual-library dirty` / `GET /manual-library/dirty` surfaces if that avoids a redundant command.
- JSON should be machine-readable; CSV should remain small and stable for operators.

### 3. Failure Recovery Guidance

- Document and expose clear recovery paths for common cases:
  - retry incremental rebuild after a transient failure
  - force full rebuild after unsafe identity reuse or Qdrant sync uncertainty
  - inspect dirty manuals before rebuilding
  - confirm stale Qdrant points were not deleted after failed payload refresh
  - roll back to local NPZ if Qdrant remains unavailable
- CLI failure output should be actionable enough that an operator can decide between retrying incremental and forcing full rebuild.

### 4. Safety And Compatibility

- Preserve the rule that dirty state clears only after a successful graph swap.
- Preserve rebuild double-buffer semantics: failed rebuilds must not replace or clear the current graph.
- Do not add a separate job queue, database, background scheduler, or durable task-history store in M21.
- Do not expose raw chunk text, vectors, secrets, local credentials, high-cardinality candidate ids, or raw Qdrant payload dumps in status summaries.
- Avoid changing ranking or search semantics.

### 5. Tests And Documentation

- Add tests for status/inspection responses after successful rebuild, failed incremental/Qdrant sync, and full rebuild recovery where practical.
- Keep fake Qdrant tests offline and deterministic.
- Update README or adjacent docs with a rebuild recovery runbook.

## Acceptance Criteria

- [ ] Operators can inspect current managed-library pending state from CLI and API without reading manifest files directly.
- [ ] A failed rebuild clearly reports why it failed or fell back, whether pending changes remain, and the suggested safe recovery action class.
- [ ] Rebuild task/status output includes current or last successful build id when available.
- [ ] Qdrant sync summaries remain low-cardinality and do not include raw vectors, chunk text, or candidate id lists.
- [ ] A full rebuild recovery path after failed incremental/Qdrant sync is covered by tests.
- [ ] Existing M15-M18 Qdrant failure-ordering and incremental rebuild tests still pass.
- [ ] Dirty state still clears only after successful graph swap.
- [ ] README/docs include practical commands for dirty inspection, retry incremental, force full rebuild, and Qdrant recovery checks.

## Definition Of Done

- PRD, design, and implementation checklist are complete.
- API/CLI surfaces provide a clear rebuild operations summary without breaking existing clients.
- Failure/recovery tests cover both pending-state behavior and Qdrant safety ordering.
- Documentation gives operators a short, repeatable recovery workflow.
- `uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py tests/unit/test_cli.py tests/unit/test_api.py -q` passes.
- `uv run pytest tests/ -q` passes before final handoff.

## Out Of Scope

- Durable task history across process restarts.
- A new queue, worker system, scheduler, or database.
- Live Qdrant integration tests in the default suite.
- Search/ranking tuning.
- Large UI redesign of the manual library admin page.
- Automatic recovery decisions that mutate data without an explicit operator rebuild command.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/05-13-m21-rebuild-operations-ux-failure-recovery/research/code-context.md`
- `src/tagmemorag/state.py`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/rebuild_impact.py`
- `tests/unit/test_manual_library.py`
- `tests/unit/test_manual_library_api.py`
- `tests/unit/test_cli.py`
