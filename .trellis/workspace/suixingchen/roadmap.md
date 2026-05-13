# Roadmap - suixingchen

## 2026-05-13 Post-M18 Development Plan - Completed

TagMemoRAG has now completed the Qdrant stabilization and retrieval-quality wave through M23:

- M15: point-level incremental Qdrant sync for managed-library rebuilds.
- M16: Qdrant ANN preselection as candidate generation for local WAVE-RAG ranking.
- M17: combined incremental rebuild plus ANN regression coverage.
- M18: batched Qdrant payload refresh for reused points with safe per-point fallback.
- M19: opt-in search diagnostics and operator debug metadata.
- M20: expanded product-manual eval coverage.
- M21: rebuild operations UX and failure recovery guidance.
- M22: Qdrant operations documentation and inspection tooling.
- M23: retrieval tuning experiment loop; defaults preserved based on eval evidence.

Keep the same safety posture for future work: no raw chunk text, vectors, secrets, raw query text, or high-cardinality absolute source paths in logs, reports, metrics, or debug metadata.

### Recommended Order

1. M19 Search Diagnostics / Operator Debug Metadata - completed
2. M20 Retrieval Quality Expansion - completed
3. M21 Rebuild Operations UX and Failure Recovery - completed
4. M22 Qdrant Operations Documentation and Inspection Tools - completed
5. M23 Retrieval Tuning Experiments - completed

This roadmap is now historical context. Future planning should start from the parking lot below or from a new Trellis task.

## M19 Search Diagnostics / Operator Debug Metadata

### Goal

Expose controlled search diagnostics for operators without adding noise to default responses or leaking sensitive data.

### Scope

- Add a config switch such as `search.debug_metadata_enabled=false`.
- Add CLI support such as `tagmemorag search --debug-search`.
- When enabled, include additive response metadata:
  - `search_strategy`
  - `ann_enabled`
  - `ann_candidate_count`
  - `ann_fallback_reason`
  - `source_k`
  - `steps`
  - `aggregate`
- Keep default API and CLI responses unchanged unless debug mode is explicitly enabled.
- Ensure cache behavior stays clear: cached search responses should either preserve debug metadata only for matching debug mode or bypass cache for debug requests.

### Acceptance Criteria

- Default `/search` response remains backward compatible.
- Debug-enabled API and CLI responses include low-cardinality diagnostics.
- ANN-disabled, ANN-enabled, and ANN-fallback cases are covered by tests.
- Diagnostics do not include raw query text, vectors, full source paths, raw document text, trace IDs as labels, or secrets.
- Existing search, cache, API, and CLI tests pass.

### Notes

Implemented behind explicit debug controls for API and CLI. Diagnostics remain low-cardinality and keep ANN as candidate generation only.

## M20 Retrieval Quality Expansion

### Goal

Expand evaluation coverage so future ranking, metadata, tag, rebuild, and ANN changes can be judged against realistic product-manual behavior.

### Scope

- Add multi-category fixtures beyond the current coffee-machine smoke cases:
  - refrigerator temperature/noise
  - washer error codes and maintenance
  - air-conditioner modes and cleaning
  - dishwasher cleaning and fault recovery
- Cover Chinese and English query variants where useful.
- Include expected answers/results for:
  - semantic lookup
  - tag and metadata relevance
  - anchor-boosted results
  - ANN enabled versus disabled
  - incremental rebuild before/after changed manuals
- Produce a repeatable eval report with pass/fail counts and per-query details.

### Acceptance Criteria

- Eval fixtures are deterministic and small enough for default or near-default local execution.
- Quality report is reproducible and does not require network access.
- At least one test proves ANN preselection does not remove expected final WAVE-RAG results.
- At least one test covers managed-library incremental rebuild followed by eval.
- No eval artifact stores raw secrets or machine-specific absolute paths.

### Notes

Implemented with deterministic coffee and product-manual fixtures. The eval runner uses the same `execute_search()` path as API and CLI search.

## M21 Rebuild Operations UX and Failure Recovery

### Goal

Make managed-library rebuild state easier to understand and recover from after failures, especially for Qdrant-backed incremental rebuilds.

### Scope

- Improve rebuild task summaries with concise operator-facing status fields:
  - effective mode
  - fallback reason
  - dirty manual count
  - qdrant sync summary
  - last successful build id
- Add a focused command or API endpoint to inspect pending library state.
- Document safe recovery actions:
  - retry incremental rebuild
  - force full rebuild
  - inspect dirty manuals
  - confirm stale Qdrant points were not deleted after failed payload refresh
- Preserve the rule that dirty state clears only after graph swap succeeds.

### Acceptance Criteria

- Failed rebuilds clearly show why they failed and whether pending changes remain.
- Full rebuild recovery from a failed incremental Qdrant sync is tested.
- Task/report metadata remains low-cardinality and compatible.
- Existing M15-M18 failure-ordering tests still pass.

### Notes

Implemented within the existing task registry, manifest, API, and CLI surfaces.

## M22 Qdrant Operations Documentation and Inspection Tools

### Goal

Give operators a practical guide for running and inspecting Qdrant-backed TagMemoRAG deployments.

### Scope

- Document Qdrant config fields and collection naming.
- Explain safe payload fields:
  - `kb_name`
  - `node_id`
  - `build_id`
  - `chunk_identity_key`
  - `manual_id`
  - `source_file`
  - `text_hash`
- Add an optional CLI inspection command if useful, for example:
  - show collection name
  - count local graph nodes versus Qdrant points
  - sample payload keys
  - detect missing vectors for current graph node ids
- Keep inspection output free of raw document text and vectors.

### Acceptance Criteria

- README or docs include Qdrant setup, rebuild, rollback, and inspection guidance.
- Any new inspection command uses fake-client unit tests and does not require live Qdrant in default CI.
- Existing collections remain load-compatible.

### Notes

Implemented with Qdrant setup/rollback documentation and a safe `qdrant inspect` CLI command covered by fake-client tests.

## M23 Retrieval Tuning Experiments

### Goal

Use the expanded M20 eval set to make deliberate retrieval improvements.

### Candidate Work

- Tune WAVE-RAG defaults such as `source_k`, `steps`, `decay`, `aggregate`, and anchor boost.
- Explore hybrid lexical/vector retrieval if evals show semantic-only recall gaps.
- Explore metadata-aware reranking using already-loaded graph/manual metadata.
- Consider payload-filtered Qdrant ANN only after eval coverage proves the recall risk is acceptable.

### Acceptance Criteria

- Each tuning change links to eval evidence.
- Defaults improve or preserve the aggregate eval score.
- No tuning change makes ANN remote ranking authoritative; Qdrant remains candidate generation unless a future PRD explicitly changes that contract.
- Performance stays reasonable for local development fixtures.

### Result

M23 added `eval run` search-parameter overrides and report snapshots for repeatable tuning experiments. Baseline product-manual metrics were already saturated (`recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`) under the deterministic hashing embedder, so search defaults remain unchanged. The `aggregate=sum` variant regressed product-manual recall and was rejected.

## Parking Lot

- Payload-filtered ANN for narrow metadata slices.
- Database-backed manual registry and audit timeline for larger multi-operator deployments.
- Background rebuild queue and cancellation.
- Import/export bundles for managed manual libraries.
- Admin UI improvements for rebuild history and diagnostics.
- Production deployment guide with Docker Compose, Qdrant backup notes, and observability examples.

## Current Working Guidance

- Use Trellis tasks for future milestones rather than implementing directly from this roadmap.
- For each milestone, write `prd.md`, `design.md`, and `implement.md` when the task crosses API, CLI, storage, or search layers.
- Before implementation, load backend specs through `trellis-before-dev`.
- After implementation, run focused tests first, then `uv run pytest tests/ -q`.
- Archive completed tasks before committing follow-up milestone work.
