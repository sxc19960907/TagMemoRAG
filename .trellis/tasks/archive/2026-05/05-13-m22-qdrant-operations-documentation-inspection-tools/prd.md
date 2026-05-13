# M22 Qdrant Operations Documentation and Inspection Tools

## Goal

Give operators a practical, low-risk way to understand, configure, inspect, and recover Qdrant-backed TagMemoRAG deployments.

M22 should turn the existing Qdrant vector backend, collection naming rules, safe payload contract, point-level rebuild sync behavior, M21 recovery status, and README guidance into a coherent operations workflow. Operators should be able to answer: which Qdrant collection belongs to this KB, whether the collection is reachable, whether the current graph node ids have vectors in Qdrant, which payload keys are present, and what recovery action is safe when Qdrant diverges.

## Background / Known Context

- `vector_store.provider` supports `npz` and `qdrant`.
- Qdrant config lives under `vector_store`: `qdrant_url`, `collection_prefix`, and `timeout_seconds`.
- `QdrantVectorStore.collection_name` is derived by normalizing `collection_prefix` and `kb_name` into `{safe_prefix}_{safe_kb}`.
- Qdrant points use graph `node_id` as point id.
- Safe payload fields are limited to `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`.
- Existing collections with only legacy `kb_name` and `node_id` payloads remain load-compatible because `load_kb()` retrieves vectors by graph node id and does not require rich payloads.
- Managed-library rebuilds sync Qdrant before graph/meta swap. Failed Qdrant sync keeps the old graph active and leaves dirty state pending.
- M18 added batch payload refresh for reused incremental points, with fallback to per-point `set_payload` for older clients.
- M21 added operator rebuild status fields and recovery hints through task output and `manual-library dirty`.
- Default tests use `FakeQdrantClient`; live Qdrant integration tests are not required in default CI.

## Requirements

### 1. Qdrant Operations Documentation

- Update README or adjacent docs with a practical Qdrant operations guide covering:
  - installation with optional `qdrant-client` extra
  - local Qdrant startup example
  - `vector_store` config fields and env overrides
  - collection naming rules and examples
  - what is stored locally versus in Qdrant
  - safe payload fields and explicitly unsafe fields
  - full rebuild, incremental rebuild, and payload refresh behavior
  - ANN preselection role and fallback behavior
  - rollback to local NPZ when Qdrant remains unavailable
- Include commands that map to current operator workflows:
  - inspect dirty/recovery state
  - retry incremental rebuild
  - force full rebuild
  - switch provider to NPZ
  - inspect Qdrant collection if M22 adds the command below

### 2. Optional CLI Inspection Command

- Add a focused CLI command if implementation confirms it can stay small and deterministic, for example:

  ```bash
  python -m tagmemorag qdrant inspect --kb default --config config.yaml
  ```

- JSON output should include only low-cardinality and safe fields:
  - `kb_name`
  - `provider`
  - `configured`
  - `collection_name`
  - `qdrant_url`
  - `collection_exists`
  - `graph_loaded`
  - `graph_node_count`
  - `qdrant_point_count`
  - `missing_vector_count`
  - `sample_payload_keys`
  - `payload_key_coverage` for the safe payload key set when cheap to compute
  - `last_qdrant_sync` when available from metadata or impact artifact
  - `recommendations`
- The command should not emit raw vectors, raw chunk text, full payload dumps, secrets, or high-cardinality point id lists by default.
- If missing vectors must be shown for troubleshooting, cap the list to a small deterministic sample and include `missing_vector_count`.
- The command should work with `FakeQdrantClient` in unit tests without a live Qdrant server.

### 3. API Surface Decision

- Prefer CLI-only inspection for M22 unless an existing API surface makes the same report easy to expose safely.
- If an API endpoint is added, it must require rebuild/admin-level scope and return the same safe report shape as CLI.
- Do not add a broad raw Qdrant browser, payload dump endpoint, or mutable repair endpoint.

### 4. Safety And Compatibility

- Preserve existing Qdrant collection load compatibility.
- Preserve rebuild sync ordering:
  1. upsert new/changed points
  2. refresh reused payloads
  3. delete stale points
- Do not change search ranking semantics.
- Do not introduce live Qdrant requirements into default test runs.
- Do not add a new database, scheduler, queue, or durable inspection history.
- Inspection must be read-only.

### 5. Tests

- Add fake-client unit tests for any new inspection helper/command.
- Cover:
  - expected collection name
  - graph node count versus Qdrant point count
  - missing vector detection
  - safe payload key reporting without raw payload values
  - provider not set to Qdrant produces a clear report or error
  - batch payload behavior remains compatible with existing tests
- Keep existing Qdrant storage, ANN, and rebuild tests passing.

## Acceptance Criteria

- [ ] README or docs include Qdrant setup, config, collection naming, rebuild, rollback, payload, and inspection guidance.
- [ ] Operators can inspect the target Qdrant collection and graph/vector consistency from CLI if the inspection command is included.
- [ ] Inspection output never includes raw vectors, raw chunk text, secrets, full payload dumps, or uncapped point id lists.
- [ ] Existing collections with legacy `kb_name`/`node_id` payloads remain load-compatible.
- [ ] Fake-client tests cover the inspection path without requiring live Qdrant in default CI.
- [ ] M15-M18 Qdrant sync ordering and payload refresh tests still pass.
- [ ] M21 recovery/status output remains compatible and is referenced from the runbook.

## Definition Of Done

- PRD, design, implementation checklist, and code-context research are complete.
- Any implemented inspection command is additive and read-only.
- Documentation gives operators a short repeatable workflow for setup, inspection, rebuild recovery, and NPZ rollback.
- `uv run pytest tests/unit/test_storage_state.py tests/unit/test_manual_library.py tests/unit/test_cli.py tests/unit/test_api.py -q` passes.
- `uv run pytest tests/ -q` passes before final handoff.

## Out Of Scope

- Automatic repair of Qdrant collections.
- Raw Qdrant payload/vector browsing.
- Live Qdrant integration tests in the default suite.
- Durable inspection history or background health monitoring.
- Search/ranking tuning.
- Schema migration for old Qdrant payloads beyond documenting compatibility.
- Multi-node or high-availability Qdrant deployment automation.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/05-13-m22-qdrant-operations-documentation-inspection-tools/research/code-context.md`
- `.trellis/tasks/archive/2026-05/05-13-m21-rebuild-operations-ux-failure-recovery/prd.md`
- `src/tagmemorag/storage/qdrant_vector.py`
- `src/tagmemorag/state.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/cli.py`
- `tests/unit/test_storage_state.py`
- `tests/unit/test_manual_library.py`
- `tests/unit/test_cli.py`
- `README.md`
