# design.md — M5 Manual Metadata and Tag-Aware Retrieval

## Scope

M5 adds metadata-aware indexing and retrieval while preserving the current WAVE-RAG algorithm and API behavior for callers that do not supply filters.

## Current State

```text
parse_document(path) -> list[Chunk]
build_kb(docs_dir) -> chunks -> embeddings -> build_graph -> graph nodes
search -> embed query -> wave_search(all graph nodes) -> Result[]
```

Current `Chunk` fields:

```python
text, header, path, level, start_line, source_file
```

Current `Result` fields:

```python
node_id, score, text, header, path, source_file, start_line, anchor_key
```

## Target State

```text
source file + sidecar metadata
  -> parse_document()
  -> Chunk(metadata=manual metadata)
  -> graph node attrs include metadata
  -> search filters choose eligible node ids
  -> WAVE search on induced subgraph or eligible mask
  -> optional metadata/tag boost
  -> Result(metadata=manual metadata)
```

## Data Contracts

### ManualMetadata

Recommended module: `src/tagmemorag/manuals.py`.

```python
@dataclass(frozen=True)
class ManualMetadata:
    manual_id: str
    title: str
    source_file: str
    product_category: str
    language: str = "unknown"
    brand: str = ""
    product_name: str = ""
    product_model: str = ""
    version: str = ""
    tags: tuple[str, ...] = ()
    status: str = "active"
    uploaded_at: str = ""
    checksum: str = ""
    notes: str = ""
```

Use `to_node_attrs()` / `from_dict()` helpers so graph persistence remains simple JSON.

### SearchFilters

Recommended module: `types.py` or `api.py` request-only Pydantic model.

```python
class SearchFilters(BaseModel):
    manual_id: str | None = None
    brand: str | None = None
    product_category: str | None = None
    product_model: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
```

CLI can map flags into the same dictionary.

## Metadata Loading

### Sidecar Resolution

For any source file:

```text
<stem><suffix> -> <stem>.metadata.json
```

Examples:

```text
fridge_gorenje.pdf -> fridge_gorenje.metadata.json
manual.md -> manual.metadata.json
```

### Fallback

If sidecar is absent:

- `manual_id`: normalized relative source path without suffix, or checksum if collisions occur.
- `title`: filename stem.
- `product_category`: first directory under docs root if present.
- `source_file`: relative source path.
- `language`: `unknown`.
- `tags`: empty.

### Validation

- Normalize tags to lower-kebab-case.
- Reject duplicate `manual_id` in a KB build.
- Reject non-list `tags`.
- Reject metadata for a source file outside docs root.

## Parser Integration

Option A: pass metadata into parser.

```python
parse_document(path, ..., metadata=metadata.to_node_attrs())
```

Pros: simple; chunks are complete at creation time.

Option B: parse first, attach metadata in `build_kb`.

Pros: keeps parser focused on document text.

Recommended MVP: **Option A**. `Chunk` creation is the natural boundary where source provenance is assigned, and tests can assert parser metadata preservation.

## Graph Integration

Extend `build_graph()` node attrs:

```python
manual_id=chunk.metadata.get("manual_id", "")
title=...
product_category=...
tags=list(...)
metadata=dict(chunk.metadata)
```

For UI convenience, store common fields both top-level and under `metadata`.

Compatibility:

- Existing graph JSON can load because absent attrs default to empty values.
- Existing tests should keep passing if `Result.to_dict()` only adds fields, not removes fields.

## Search Filtering

### Candidate Eligibility

Create a helper, likely in `wave_searcher.py`:

```python
def filter_node_ids(graph, filters: SearchFilters | Mapping[str, Any]) -> set[int]:
    ...
```

Rules:

- Empty filters -> all nodes.
- Scalar filters are exact string matches after normalization.
- Tags: requested tags match if any requested tag is present on node.
- Other fields AND together with tags.

### WAVE Search Strategy

MVP should avoid rewriting WAVE propagation deeply. Two feasible choices:

1. Build an induced subgraph and vector slice for eligible nodes.
2. Add `eligible_node_ids` parameter to `wave_search()` and mask source selection/propagation.

Recommended: **Option 2** if implementation remains small. It preserves original node ids in results and avoids remapping anchors. If it becomes messy, use an induced subgraph helper that carries original ids.

Contract:

- Source nodes must come from eligible ids.
- Propagation should stay within eligible ids for hard filters.
- Empty eligible set returns `[]`.

## Tag Boost

Perform boost after WAVE scores:

```text
final_score = wave_score
            + field_match_count * metadata_field_boost
            + tag_match_count * tag_boost
```

Suggested config:

```yaml
retrieval:
  metadata_field_boost: 0.05
  tag_boost: 0.03
```

Alternative: add under existing `search` config to avoid a new top-level section:

```yaml
search:
  metadata_field_boost: 0.05
  tag_boost: 0.03
```

Recommended MVP: add to `SearchConfig` because this behavior is part of ranking.

## Cache Key Updates

`_compute_cache_key()` must include canonical filters:

```json
{"brand":"gorenje","product_category":"fridge","tags":["temperature-setting"]}
```

Sort tag lists before hashing.

## API Changes

Request:

```json
{
  "question": "冰箱温度怎么调",
  "kb_name": "fridge",
  "filters": {
    "product_category": "fridge",
    "product_model": "NRK6192",
    "tags": ["temperature-setting"]
  }
}
```

Response result adds:

```json
{
  "manual_id": "gorenje-nrk6192-zh-cn-v1",
  "manual_title": "Gorenje refrigerator manual",
  "brand": "Gorenje",
  "product_category": "fridge",
  "product_model": "NRK6192",
  "language": "zh-CN",
  "version": "v1",
  "tags": ["temperature-setting"]
}
```

## CLI Changes

Add flags to `search`:

```bash
tagmemorag search "冰箱温度怎么调" \
  --kb fridge \
  --category fridge \
  --model NRK6192 \
  --tag temperature-setting
```

## Testing Plan

- `test_manual_metadata.py`
  - sidecar load
  - fallback metadata
  - tag normalization
  - duplicate manual id rejection
- `test_parser.py`
  - metadata preserved on chunks for text and PDF
- `test_storage_state.py`
  - graph nodes persist metadata through save/load
- `test_graph_wave.py` or `test_tag_search.py`
  - filtered search excludes non-matching nodes
  - empty filters preserve old behavior
  - tag boost changes ordering deterministically
- `test_api.py`
  - `/search` filters are honored
  - cache key differs with filters
- `test_cli.py`
  - CLI filter flags reach search path

## Rollout / Compatibility

- Existing KBs without metadata should still load and search.
- Existing clients can omit `filters`.
- Existing eval suites keep working because source/header/text matching remains.
- New result fields are additive.

## Risks

- Filtering before graph propagation can reduce useful cross-manual edges. This is intended for hard product filters.
- Free-form tags can become messy. M5 should normalize and document tags, but taxonomy governance is follow-up.
- PDF page chunks are coarse; metadata improves routing but not within-page precision. Better PDF layout chunking can follow.

## Rollback

- Disable filters by ignoring `SearchRequest.filters`.
- Keep metadata on graph nodes; it is additive and harmless.
- If tag boost hurts ranking, set boost defaults to `0.0`.
