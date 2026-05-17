# Implementation Plan — General RAG metadata narrowing

> Parent documents: [prd.md](./prd.md) · [design.md](./design.md)

## Stages

### Stage 1: Generic metadata contracts

- [x] Add a generic `DocumentMetadata` / metadata normalization module.
- [x] Add conversion helpers from existing `ManualMetadata` to generic metadata.
- [x] Preserve existing manual metadata fields in graph nodes and result objects.
- [x] Add unit tests for normalization, identity tags, and legacy compatibility.

### Stage 2: Metadata index

- [x] Implement `MetadataIndex.from_graph(graph)` as a pure helper.
- [x] Index common fields, manual legacy fields, attributes, and tags.
- [x] Add lookup helpers for exact normalized value and alias lookup.
- [x] Add unit tests for dedupe, node/doc mapping, and multi-doc same-value cases.

### Stage 3: Query narrowing rules

- [x] Implement product-manual query entity detection for model / brand / category.
- [x] Add category alias map for zh/en product manual terms.
- [x] Implement `NarrowingDecision` with hard filters, boost filters, detected entities, and fallback reasons.
- [x] Ensure explicit filters win over inferred filters.
- [x] Ensure empty-candidate hard filters fall back safely.
- [x] Add unit tests for exact model, brand-only, category-only, conflict, ambiguous, and no-match behavior.

### Stage 4: Search integration

- [x] Add `SearchConfig` switches for metadata narrowing and policies.
- [x] Integrate narrowing into API search before `execute_search()`.
- [x] Integrate narrowing into CLI search before `execute_search()`.
- [x] Thread debug diagnostics into `search_debug_payload` or API/CLI wrapper payload.
- [x] Preserve existing explicit filter behavior.
- [x] Add API / CLI tests.

### Stage 5: Product manual identity tags

- [x] Add namespaced identity tags during manual metadata conversion or chunk metadata preparation.
- [x] Ensure tag governance / tag normalization handles `brand:`, `model:`, `category:`, and `doc:` tags consistently.
- [x] Confirm wave/tag boost does not accidentally treat all identity tags as unbounded global concepts.
- [x] Add tests for identity tags in graph node metadata.

### Stage 6: Evaluation

- [x] Add regression cases showing model-specific queries route to the correct manual/category.
- [ ] Re-run `scripts/diag_realmanuals_eval.py` on a rebuilt KB or documented fixture.
- [ ] Record before/after metrics in task research.
- [ ] Keep `realmanuals.jsonl` informational unless proper ground truth is added.

### Stage 7: Docs and finish

- [x] Update README search/filter docs.
- [ ] Update architecture docs with generic metadata/narrowing contract.
- [x] Run full tests.
- [x] Run hashing eval CI.
- [ ] Decide whether to update `.trellis/spec/backend/*` with a reusable metadata schema guideline.
- [ ] Commit changes.

## Validation Commands

```bash
# Focused unit tests (names TBD after implementation)
.venv/bin/python -m pytest tests/unit/test_metadata_narrowing.py tests/unit/test_document_metadata.py -q

# API/CLI regression tests
.venv/bin/python -m pytest tests/unit/test_api.py tests/unit/test_cli.py -q

# Full project tests
.venv/bin/python -m pytest tests/ -q

# Offline eval gate
.venv/bin/python scripts/run_eval_ci.py

# Informational real-manual routing diagnostic, after rebuilding with current model/config if needed
.venv/bin/python scripts/diag_realmanuals_eval.py --reuse-built-kb
```

## Review Gates

- **Gate A (after Stage 1/2)**: Generic metadata and index are additive; existing manual sidecars still parse.
- **Gate B (after Stage 3)**: Narrowing rules are deterministic and have safe fallback for ambiguous / conflicting matches.
- **Gate C (after Stage 4)**: API/CLI debug output shows inferred filters without leaking sensitive data.
- **Gate D (after Stage 6)**: Realmanuals-style routing improves for model-specific queries or the task explains why not.

## Rollback

- Config rollback: set `search.metadata_narrowing_enabled=false`.
- Code rollback: remove integration call while keeping generic metadata helpers if they are harmless.
- Data rollback: identity tags are derived during build; rebuilding with the feature disabled returns to prior metadata shape.

## Notes

- Do not rename `/manuals` in this task. That is a platform UX/API migration and should be separate.
- Do not add public `/documents` routes in this task; keep the public surface manual-compatible while implementing the generic internals.
- Do not add LLM query parsing in this task. Deterministic metadata narrowing is the MVP.
- Treat product manuals as one domain adapter, not as the generic model itself.
