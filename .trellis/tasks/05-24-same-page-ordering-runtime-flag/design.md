# Design

## Boundary

The runtime feature is default-off. The default path must preserve existing
retrieval result order and response shape. When enabled, the feature applies a
local deterministic reorder to the `Result` sequence before evidence/citations
are built.

## Configuration

Add fields to `SearchConfig`:

- `same_page_ordering_enabled: bool = False`
- `same_page_ordering_min_group_size: int = Field(default=2, ge=2)`

This keeps the feature with retrieval ranking settings and allows env/YAML
overrides through existing settings loading.

## Runtime Flow

1. `/retrieve` obtains `candidates_used` from base search or external reranker.
2. `build_retrieve_response` receives an optional `SamePageOrderingOptions`.
3. If options are absent or disabled, order is unchanged.
4. If enabled:
   - compute bounded usefulness signals from result text/header and query text
   - detect repeated `source_file`/`header` dominance
   - check first useful result rank
   - reorder only if first useful result is below rank 1
   - keep rank-1 hits unchanged
5. Evidence, citations, context pack, and answerability are built from the
   possibly reordered sequence.

## Usefulness Signal

Reuse a small pure runtime module rather than importing CLI/report diagnostics.
The runtime module emits no raw diagnostics and returns only reordered `Result`
objects.

## Rollback

Rollback is disabling the flag. Code rollback removes the new runtime module,
configuration fields, and the one call site.
