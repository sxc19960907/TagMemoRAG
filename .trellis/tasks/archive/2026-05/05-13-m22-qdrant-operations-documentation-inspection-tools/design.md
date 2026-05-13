# design.md - M22 Qdrant Operations Documentation and Inspection Tools

## Scope

M22 is an operator experience task for Qdrant-backed deployments. The first priority is documentation; the implementation work should stay limited to a read-only inspection surface if it materially improves operator confidence.

The task should reuse existing config, `QdrantVectorStore`, local graph/meta artifacts, M21 dirty/recovery status, and fake-client test infrastructure. It should not introduce a separate Qdrant admin subsystem.

## Current Qdrant Flow

```text
config.yaml
  -> vector_store.provider=qdrant
  -> QdrantVectorStore(collection_prefix, kb_name)
  -> collection_name("{safe_prefix}_{safe_kb}")

save/rebuild
  -> graph/meta/anchors local JSON artifacts
  -> vectors in Qdrant
  -> safe payload fields attached to points

managed-library rebuild
  -> build candidate graph
  -> Qdrant sync before graph/meta swap
       -> upsert new/changed points
       -> refresh reused payloads
       -> delete stale old ids
  -> save metadata artifacts
  -> graph swap
  -> clear dirty manifest
```

Important safety property: Qdrant sync completes before local graph/meta artifacts are swapped. If Qdrant sync fails, the old graph remains active and dirty changes remain pending.

## Proposed Operator Flow

```text
operator enables qdrant
  -> read config/runbook
  -> rebuild KB
  -> inspect dirty/rebuild status
  -> inspect Qdrant collection consistency
       collection name
       point count
       graph node count
       missing vector count
       payload key sample/coverage
  -> choose action:
       retry incremental
       force full rebuild
       switch provider=npz until Qdrant is healthy
```

## Inspection Report Contract

If implemented, the CLI report should be JSON by default:

```json
{
  "kb_name": "default",
  "provider": "qdrant",
  "configured": true,
  "collection_name": "tagmemorag_default",
  "qdrant_url": "http://localhost:6333",
  "collection_exists": true,
  "graph_loaded": true,
  "graph_node_count": 42,
  "qdrant_point_count": 42,
  "missing_vector_count": 0,
  "missing_vector_sample": [],
  "sample_payload_keys": ["build_id", "chunk_identity_key", "kb_name", "manual_id", "node_id", "source_file", "text_hash"],
  "payload_key_coverage": {
    "kb_name": 42,
    "node_id": 42,
    "build_id": 42,
    "chunk_identity_key": 42,
    "manual_id": 42,
    "source_file": 42,
    "text_hash": 42
  },
  "last_qdrant_sync": {
    "provider": "qdrant",
    "strategy": "point_incremental",
    "points_upserted": 1,
    "points_deleted": 0,
    "points_reused": 41,
    "fallback_reason": ""
  },
  "recommendations": []
}
```

### Field Rules

- `collection_name` must use `collection_name(cfg.vector_store.collection_prefix, kb_name)`.
- `graph_node_count` comes from local graph state if `load_kb()` succeeds.
- `qdrant_point_count` can be computed through Qdrant scroll when available.
- `missing_vector_count` compares graph node ids against retrieved/available point ids.
- `sample_payload_keys` reports keys only, not values.
- `payload_key_coverage` is optional if expensive for a real client; when present, it should count only the safe payload key set.
- `missing_vector_sample` must be capped and deterministic.
- `last_qdrant_sync` should reuse low-cardinality sync summaries from meta or `rebuild_impact.json`.

## CLI Design

Recommended command:

```bash
python -m tagmemorag qdrant inspect --kb default --config config.yaml
```

Behavior:

- If `vector_store.provider != qdrant`, return a JSON report with `configured=false`, provider value, collection name derived from config, and a recommendation to set `vector_store.provider=qdrant`; exit code can remain `0` for inspection.
- If local graph is not loaded from disk, report `graph_loaded=false` and still show config/collection reachability when possible.
- If Qdrant is unreachable, return a structured report with `collection_exists=false` or `error` using safe fields; exit code should be non-zero only when the command cannot produce a meaningful inspection report.
- Keep output machine-readable JSON; human formatting can be deferred.

Implementation placement:

- Put reusable inspection logic in the narrowest shared module. A small `qdrant_ops.py` module is reasonable if both CLI and tests need the report without importing CLI.
- Reuse `QdrantVectorStore` methods where practical, but avoid calling `load_kb()` in a way that hides missing-vector details. Inspection may need to read local graph/meta first and query Qdrant separately.
- Do not expose this through API unless CLI-only proves insufficient.

## Documentation Design

README should become the operator entry point and include:

- concise setup commands
- config examples
- collection naming examples
- local vs Qdrant artifact boundaries
- safe payload key list
- rebuild sync ordering
- M18 batch payload note
- M21 recovery status references
- inspection command examples
- NPZ rollback path
- troubleshooting matrix

Avoid burying operational commands only in milestone prose; make them copyable.

## Testing Design

Use `FakeQdrantClient` from `tests/unit/test_storage_state.py` or extend it carefully.

Recommended tests:

- `test_qdrant_inspect_reports_collection_and_counts`
- `test_qdrant_inspect_detects_missing_graph_vectors`
- `test_qdrant_inspect_reports_payload_keys_without_values`
- `test_qdrant_inspect_non_qdrant_provider_is_clear`
- CLI wrapper test in `tests/unit/test_cli.py`

The fake client may need `scroll(..., with_payload=True)` support if payload key sampling is implemented. Keep fake behavior close to the real client shape without adding network dependencies.

## Compatibility

- Existing Qdrant point ids remain graph node ids.
- Existing payload sanitizer remains authoritative.
- Legacy payloads with only `kb_name` and `node_id` must not be treated as corruption.
- Inspection should identify missing optional payload keys as a recommendation, not a hard failure.

## Security And Privacy

Allowed output:

- counts
- collection name
- provider/config status
- Qdrant URL from config
- safe payload key names
- capped node id samples only when needed
- low-cardinality sync strategy/fallback fields

Forbidden output:

- raw vectors
- raw chunk text
- full payload values
- API keys or environment secret values
- unbounded point id lists
- exception traces

## Rollout / Rollback

Rollout is low risk because documentation and read-only CLI inspection are additive.

Rollback can remove the new CLI command and docs without changing vector persistence, rebuild ordering, or search behavior. If the inspection report becomes too broad, keep the README updates and defer the command.

## Open Questions

- Should M22 expose API inspection in addition to CLI?
  - Recommendation: CLI only for M22. API can follow later if the admin UI needs it.
- Should missing vector samples include node ids?
  - Recommendation: include a small capped sample, because node ids are already operational ids in graph/Qdrant contracts. Do not include manual text or payload values.
- Should non-Qdrant configs make `qdrant inspect` fail?
  - Recommendation: return a clear report with `configured=false` and exit `0`, because this is an inspection command and the operator may be checking config state.
