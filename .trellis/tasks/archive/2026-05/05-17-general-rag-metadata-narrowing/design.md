# Technical Design — General RAG metadata narrowing

> Parent document: [prd.md](./prd.md)

## 1. Design Intent

This task should add a generic metadata and narrowing layer without ripping out the existing manual-library code. The current manual APIs are a useful first product surface; the new layer should sit underneath search/build and make future domains possible.

The key design principle:

> Product manual identity is one domain schema over a generic document metadata model, not the platform's only metadata model.

## 2. Current Data Flow

```text
source files + sidecars
  -> load_manual_metadata()
  -> parse_document(..., metadata=dict(manual_metadata))
  -> Chunk(metadata=manual fields)
  -> build_graph()
  -> graph node metadata + manual-specific top-level fields
  -> execute_search(filters=explicit user filters)
  -> filter_node_ids() only checks fixed manual fields + tags
  -> wave_search()
```

Existing strengths:

- Chunks can already carry arbitrary `metadata`.
- Graph nodes preserve that metadata.
- Search already has a pre-ranking eligible node filter.
- API / CLI already accept explicit manual filters.

Current gap:

- There is no generic metadata contract.
- Query text is not used to infer filters.
- The fixed filter field list is manual-shaped.

## 3. Proposed Data Flow

```text
source files + sidecars
  -> domain metadata loader / adapter
  -> DocumentMetadata(common fields + attributes)
  -> Chunk(metadata={common fields, attributes, legacy fields})
  -> build_graph()
  -> MetadataIndex.from_graph(state.graph)
  -> QueryNarrower.infer(query, metadata_index, explicit_filters)
  -> explicit filters + inferred hard filters + boost hints
  -> execute_search(..., filters=resolved_filters, narrowing_debug=...)
  -> wave_search()
```

## 4. Core Contracts

### 4.1 DocumentMetadata

Add a generic representation, likely in a new module such as `document_metadata.py`:

```python
@dataclass(frozen=True)
class DocumentMetadata:
    doc_id: str
    title: str
    source_file: str
    domain: str = "generic"
    doc_type: str = "document"
    language: str = "unknown"
    status: str = "active"
    tags: tuple[str, ...] = ()
    attributes: Mapping[str, str | tuple[str, ...]] = field(default_factory=dict)
```

Rules:

- Common fields are for platform-level operations.
- `attributes` is for schema/domain-specific fields.
- All indexable values should have normalized forms.
- Existing manual fields can be mirrored both as legacy top-level metadata and under `attributes`.

### 4.2 Domain schema adapters

MVP adapter:

```text
ManualMetadata -> DocumentMetadata(domain="product_manual", doc_type="manual")
```

Mapping:

| Manual field | Generic target |
|---|---|
| `manual_id` | `doc_id`, `attributes.manual_id` |
| `title` | `title` |
| `source_file` | `source_file` |
| `brand` | `attributes.brand`, identity tag |
| `product_category` | `attributes.product_category`, identity tag |
| `product_model` | `attributes.product_model`, identity tag |
| `language` | `language` |
| `status` | `status` |
| `tags` | `tags` |

Identity tags:

- `brand:<normalized-brand>`
- `model:<normalized-model>`
- `category:<normalized-category>`
- `doc:<normalized-doc-id>`
- `manual:<normalized-manual-id>` (legacy-friendly alias)

These tags are not a replacement for structured fields; they let tag-based machinery participate.

### 4.3 MetadataIndex

Add an in-memory index built from graph node metadata:

```python
@dataclass(frozen=True)
class MetadataValueHit:
    field: str
    value: str
    normalized: str
    doc_ids: frozenset[str]
    node_ids: frozenset[int]

@dataclass
class MetadataIndex:
    by_field_value: dict[tuple[str, str], MetadataValueHit]
    aliases: dict[str, list[tuple[str, str]]]
```

Index fields:

- common: `doc_id`, `domain`, `doc_type`, `language`, `tags`
- legacy/manual: `manual_id`, `brand`, `product_category`, `product_model`
- attributes: `attributes.<key>` or a simpler flattened key namespace

MVP can build this lazily per search from `state.graph`, but preferred is to cache in `GraphState.meta` or a lightweight runtime cache if construction cost becomes visible. Since graph sizes are currently small, simple is fine.

### 4.4 QueryNarrower

New pure helper module, e.g. `metadata_narrowing.py`.

Inputs:

- `query_text`
- `metadata_index`
- explicit filters from request / CLI
- settings

Output:

```python
@dataclass(frozen=True)
class NarrowingDecision:
    hard_filters: dict[str, object]
    boost_filters: dict[str, object]
    detected: tuple[DetectedEntity, ...]
    mode: Literal["none", "hard_filter", "boost", "mixed"]
    before_count: int
    after_count: int | None
```

MVP entity rules for product manuals:

1. **Exact model detection**
   - Source values: `product_model` and model aliases from metadata index.
   - Match case-insensitive alphanumeric tokens, preserving model punctuation variants where practical.
   - If exactly one doc/model matches: hard filter by `product_model` or `doc_id/manual_id`.
   - If multiple docs match the same model: hard filter all matching docs.

2. **Brand detection**
   - Source values: `brand`.
   - If brand is unique and no stronger signal exists: boost by default, hard filter only if configured.

3. **Category detection**
   - Source values: `product_category` plus alias map.
   - Alias examples: `冰箱 -> refrigerator`, `洗衣机/洗衣機 -> washer`, `干衣机/乾衣機 -> dryer`, `烤箱 -> oven`.
   - In `domain=product_manual` KBs: category can hard filter if it leaves enough candidates.
   - In generic KBs: category-like terms should boost unless schema explicitly marks them as hard filters.

4. **Conflict handling**
   - Explicit user filters always win.
   - Inferred hard filters must not contradict explicit filters; if they do, do not apply inferred filters and emit debug reason `conflicts_with_explicit_filter`.
   - If a hard filter empties the candidate set, fall back to no inferred hard filter and emit debug reason `empty_candidate_fallback`.

### 4.5 Search integration

Integration point should be before `execute_search()` calls `filter_node_ids()`.

API flow:

```text
SearchRequest.filters
  -> governed explicit filters
  -> MetadataIndex.from_graph(state.graph)
  -> QueryNarrower.infer(...)
  -> merged filters passed to execute_search
  -> debug payload includes narrowing decision
```

CLI flow:

```text
search args (--brand/--category/--model/--tag)
  -> explicit filters
  -> same narrowing helper
```

Eval flow:

- Default eval should use the same behavior unless an eval explicitly disables auto narrowing.
- Add config switch to disable auto narrowing for A/B testing.

### 4.6 Config

Add search config keys:

```yaml
search:
  metadata_narrowing_enabled: true
  metadata_narrowing_mode: auto
  metadata_narrowing_brand_policy: boost_if_not_unique
  metadata_narrowing_category_policy: hard_filter_product_manual
  metadata_narrowing_min_candidates: 1
```

Keep defaults conservative if risk is high. Recommended MVP default:

- Enable for CLI/API search.
- Tests should show no behavior change when no entity is detected.
- Allow config off switch for rollback.

## 5. Compatibility Plan

- Do not remove `ManualMetadata`.
- Do not remove `/manuals`.
- Do not add public `/documents` routes in this task; that migration is a follow-up after the internal generic metadata contract is proven.
- Keep `Result` manual fields populated.
- Existing sidecars remain valid.
- New generic fields are additive.
- Existing explicit filters remain accepted.
- Saved KBs without generic metadata should still load; narrowing can derive generic fields from legacy fields.

## 6. API / Debug Shape

Search debug payload should add a bounded, safe object:

```json
{
  "metadata_narrowing": {
    "enabled": true,
    "mode": "hard_filter",
    "detected": [
      {"type": "product_model", "value": "HR6FDFF701SW", "field": "product_model", "confidence": 1.0}
    ],
    "hard_filters": {"product_model": "HR6FDFF701SW"},
    "boost_filters": {},
    "before_count": 527,
    "after_count": 86,
    "fallback_reason": ""
  }
}
```

Do not include raw document snippets, full source-file lists, or secrets.

## 7. Evaluation Plan

Add a small eval/regression suite around the realmanuals fixture shape:

- `HR6FDFF701SW ice maker cubed crushed` should narrow to refrigerator/manual.
- `DHGA901NL laundry not dried` should narrow to dryer/manual.
- `ASKO W6564 洗劑粉盒` should narrow to washer/manual.
- Ambiguous category-only query should not break no-filter fallback.
- Explicit contradictory filter should win or fail safely according to final contract.

For the archived realmanuals KB, rerun:

```bash
.venv/bin/python scripts/diag_realmanuals_eval.py --reuse-built-kb
```

Expected direction after implementation:

- top1 category hit improves from 0.667.
- model-specific queries should route top1 to the correct manual/category.

## 8. Rollout / Rollback

Rollout:

1. Add generic metadata helpers and tests.
2. Add index and query narrower behind config flag.
3. Enable for product-manual domain.
4. Update API/CLI debug output.
5. Add eval coverage.

Rollback:

- Set `search.metadata_narrowing_enabled=false`.
- Explicit filters and current search pipeline continue to work.

## 9. Design Risks

- Over-filtering can hide valid answers if entity detection is too aggressive.
- Category aliases are language/domain-specific; keep alias maps scoped to schemas.
- Generic metadata could become too abstract if we try to solve every domain at once.
- Identity tags can pollute tag cooccurrence if not namespaced (`model:` / `brand:` / `category:` are required).

## 10. Future Extensions

- Public `/documents` API parallel to `/manuals`.
- Domain schema registry loaded from YAML.
- User-defined metadata fields and facet discovery.
- LLM-assisted query understanding as optional second-stage narrowing.
- Parser plugin registry for PDF/HTML/Office/code/wiki data sources.
