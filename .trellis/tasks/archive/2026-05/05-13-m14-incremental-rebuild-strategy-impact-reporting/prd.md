# M14 Incremental Rebuild Strategy and Impact Reporting

## Goal

Make the M13 incremental rebuild path smarter and easier to operate by adding chunk-level reuse identity, threshold-based `auto` mode, rebuild impact reporting, and dirty-state export. Operators should understand what will rebuild, why `auto` picked full or incremental, and what changed after a rebuild without reading manifest files by hand.

## Background / Known Context

- M13 added durable dirty manual tracking in `.tagmemorag-library.json`.
- M13 added managed-library rebuild modes: `full`, `incremental`, and `auto`, with `full` remaining the compatibility default.
- The current incremental path reuses chunks/vectors by unchanged manual, parses/embeds dirty active manuals, rebuilds graph topology globally, and saves full final artifacts.
- Current task metadata reports requested/effective mode, dirty count, fallback reason, reused chunk count, and embedded chunk count.
- M13 follow-up ideas include persistent chunk identity, threshold-based auto mode, rebuild impact reports, dirty-state export, and Qdrant point-level cleanup.

## Requirements

### 1. Persistent Chunk Identity Map

- Persist a chunk identity map per KB, keyed by stable fields such as `manual_id`, `source_file`, `header/path`, `start_line` where useful, and text hash.
- Use the identity map to reuse unchanged chunks/vectors within dirty manuals when metadata changed but chunk text did not.
- Preserve correctness when source files are renamed, manuals are disabled/deleted, or chunks split/merge after parser config changes.
- If identity map is missing, stale, schema-incompatible, or ambiguous, fall back to the existing M13 manual-level reuse or full rebuild.

### 2. Threshold-Based Auto Mode

- Give `mode=auto` explicit policy semantics.
- Choose incremental when dirty manual count and estimated dirty chunk count are below configured thresholds.
- Choose full rebuild when thresholds are exceeded or safe incremental prerequisites are missing.
- Surface `auto_decision_reason` in rebuild task metadata and saved `meta.json`.
- Keep `full` as the default API/CLI behavior unless a later task changes defaults.

### 3. Rebuild Impact Report

- Produce a structured impact report for managed-library rebuilds.
- Include added, removed, changed, reused, and embedded counts at manual and chunk granularity.
- Include dirty manual operations from the manifest and final outcome per dirty manual.
- Avoid storing or returning raw chunk text in the impact report.
- Expose the report through rebuild task response and persisted metadata or a companion artifact under `data/{kb}/`.

### 4. Dirty State Export

- Add an API and CLI export path for current dirty manual state.
- Support JSON output at minimum; CSV output is desirable for operations workflows.
- Include manual ID, source file, operation, updated time, checksum, and current library status/searchability where available.
- Keep auth scopes and KB allowlists consistent with existing manual-library read/rebuild permissions.

### 5. Compatibility and Safety

- Preserve M13 zero-downtime rebuild behavior: failed rebuilds keep old graph and dirty state.
- Do not change WAVE-RAG ranking semantics.
- Do not log raw manual text, vectors, API keys, or high-cardinality source paths as metric labels.
- Continue to support old manifests and KBs that lack the chunk identity map.

## Acceptance Criteria

- [ ] Incremental rebuild can reuse unchanged chunks inside a dirty manual when text identity matches.
- [ ] Unsafe or missing identity map cases fall back with structured reason metadata.
- [ ] `mode=auto` chooses incremental or full using configured thresholds and reports its decision reason.
- [ ] Rebuild task metadata includes a non-textual impact report summary.
- [ ] A persisted impact artifact or metadata entry is available after successful managed-library rebuilds.
- [ ] API and CLI can export dirty manual state as JSON.
- [ ] CSV dirty export is implemented or explicitly documented as deferred.
- [ ] Existing M13 full/incremental behavior remains backward compatible.
- [ ] Tests cover chunk identity reuse, auto threshold decisions, impact report counts, dirty export, fallback paths, and auth.
- [ ] Documentation explains auto mode, impact reports, and dirty export.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Focused unit/API/CLI tests pass.
- `uv run pytest tests/ -q` passes.
- README and backend spec are updated for any durable file contracts.

## Out of Scope

- Database-backed audit history.
- Background file watchers or scheduled rebuilds.
- Manual diff visualization in the admin UI beyond showing summary counts.
- Changing WAVE-RAG ranking, graph edge semantics, or search response ranking behavior.
- Distributed rebuild coordination or multi-replica cache invalidation.
- Qdrant point-level delete/update optimization, unless it is small enough to include safely after the core M14 scope.

## Open Questions

- Should CSV dirty export be required in MVP or left as a follow-up after JSON export?
- Should the chunk identity map live in `data/{kb}/` with built artifacts, under the managed library root, or both?
