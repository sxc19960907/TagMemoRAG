# Design — Production Chunker

## Scope

Phase 2 upgrades chunking while preserving the existing parser/build/search architecture. `Chunk` remains the retrieval unit. The task may add helper functions and config fields, but it must not introduce durable `DocumentElement` storage or a new retrieval API.

## Proposed MVP

Deliver three focused improvements:

1. **Sentence-aware split**
   - Prefer paragraph boundaries.
   - Then prefer sentence boundaries for English and CJK punctuation.
   - Use hard splitting only as the last fallback for pathological long spans.

2. **Deterministic overlap**
   - Add a config value such as `parser.overlap_chars`.
   - Apply overlap between split siblings from the same original chunk.
   - Keep overlap bounded so chunk growth is predictable.

3. **Markdown table-aware handling**
   - Detect simple pipe tables in Markdown/TXT text.
   - Keep small tables together when possible.
   - Split large tables on row boundaries and repeat the header in split table chunks when needed.
   - Mark chunks with metadata such as `chunk_kind="table"` or `split_reason="table_row_boundary"` when safe.

## Data Flow

```text
parse_document()
  -> raw Chunk with parser metadata
  -> _post_process()
       -> sentence/table aware splitting
       -> overlap application
       -> short-chunk merge where safe
  -> _with_lineage()
  -> build_graph()
  -> search/storage unchanged
```

Lineage should continue to be generated after post-processing so split chunks get distinct `chunk_id`s.

## Config

Add parser config fields only if needed:

- `overlap_chars: int = 0` or a conservative default.
- Optional table settings only if required by implementation, e.g. `table_header_repeat: bool = True`.

Config changes must be included in the parser signature used by `chunk_identity.json` so incremental rebuilds do not reuse incompatible chunk identities.

## Compatibility

- Existing `max_chars` and `min_chars` retain their meaning.
- Existing tests that only assert high-level chunk behavior should remain valid.
- New chunk metadata is additive.
- `/search` response shape remains unchanged except metadata additions.

## Direction Gate Checks

### Gate 0: Before Implementation

Confirm:

- The task remains a chunker task, not a retrieval/evidence task.
- Improvements are profile-neutral and not appliance-specific.
- Product-manual quality remains the first validation target.

### Gate 1: After Core Chunker Changes

Inspect:

- Markdown heading chunks.
- Plain TXT chunks.
- PDF page chunks.
- Markdown table chunks.

Confirm:

- Sentence boundaries are preferred.
- Overlap is bounded.
- Table rows are not cut mid-row when avoidable.
- Lineage remains present and distinct.

### Gate 2: Before Commit

Run:

- Focused parser/storage/incremental tests.
- Full tests.
- Eval CI.

Document:

- Chunk-count changes.
- Retrieval metric changes.
- Any intentional trade-offs.

## Deferred Decisions

- Whether parent chunks enter vector indexes belongs to Phase 2.5.
- Whether table rows become separate index objects belongs to Phase 2.5.
- Whether to use embedding-based semantic chunking belongs to a later eval-driven task.
