# Design — Indexing Strategy and Index Schema

## Direction Check

Phase 2.5 is a contract-setting task. It exists to prevent Phase 3 `/retrieve` from being built on vague indexing assumptions.

This task should not change runtime retrieval behavior. It should decide and document the indexing model so future implementation can be incremental, testable, and reversible.

## ID Full-Map

| ID | Stability | Owner | Current / Future Use | Rule |
| --- | --- | --- | --- | --- |
| `doc_id` | Durable document identity | metadata/manual library | filtering, evidence source, context source | Prefer explicit metadata. Managed-library rename keeps `doc_id`; unmanaged path rename may become new doc unless metadata pins it. |
| `chunk_id` | Durable retrieval-unit identity | parser/chunker lineage | evidence refs, future `/retrieve`, Qdrant payload | Derived from `doc_id`, parser profile/version, source identity, section path, page range, start position, and text fingerprint. |
| `element_ids` | Durable-ish source-structure identity | parser/chunker lineage | future evidence and parent/child mapping | Synthetic in Phase 1/2; future Document IR should replace with real element ids while keeping compatibility. |
| `parent_chunk_id` | Future durable context identity | hierarchical chunker | context expansion, evidence grouping | Not implemented yet. Derived from doc/section/page/span/version; parent chunks should not be graph nodes by default. |
| `asset_id` | Future durable asset identity | asset pipeline | visual evidence, OCR/caption index | Derived from `doc_id`, asset type, page/bbox/fingerprint, source checksum, and asset generation version. |
| `chunk_identity_key` | Build-artifact reuse key | `chunk_identity.json` | incremental rebuild/vector reuse | Existing compatibility bridge. It is not an API-facing evidence id. |
| `node_id` | Rebuild-local graph id | graph builder | in-memory graph/vector row | Never durable. Keep internal to `/search` compatibility/debug only. |
| Qdrant point id | Currently rebuild-local numeric id | vector store sync | ANN candidate generation | Keep numeric `node_id` now. Future migration can derive UUID/int64 from `chunk_id`, but must be a dedicated migration task. |
| `citation_id` | Request-scoped | `/retrieve` evidence builder | response citation refs | Generated per response; points to durable `doc_id`/`chunk_id`/future `asset_id`. |
| `context_item_id` | Request-scoped | context builder | Agent context pack | Generated per response; points to evidence/citations, not durable. |

## Index Inventory

### Current Indexes

- **Text vector index**
  - Current: every graph node / retrieval chunk.
  - Key: `node_id` today, future stable key from `chunk_id`.
  - Payload: safe lineage and metadata fields.

- **Lexical index**
  - Current: in-memory scan over graph node text/header/path/metadata aliases.
  - Key: `node_id`.
  - Future: may become BM25-like, but should keep safe debug surfaces.

- **Metadata/facet index**
  - Current: graph node metadata plus metadata narrowing.
  - Key: `doc_id`, `manual_id`, brand/category/model/language/tags/attributes.
  - Future: `section_path`, `page_start/page_end`, `chunk_kind`, `parser_profile`, and ACL-friendly fields.

- **Graph topology index**
  - Current: chunk graph with semantic, consecutive, parent_child, sibling edges.
  - Key: `node_id`.
  - Future: graph nodes remain child/retrieval chunks unless eval proves parent graph nodes help.

- **Qdrant payload index**
  - Current: safe payload fields for ANN filtering/debug.
  - Key: numeric point id currently equal to `node_id`.
  - Future: richer safe payload fields, still no raw text.

### Future Indexes

- **Parent/context chunk index**
  - Default: not in vector index, not graph node.
  - Use as context expansion after child chunk hit.
  - May enter vector index only if eval proves parent retrieval improves answerability without precision loss.

- **Table index**
  - Current Phase 2: table chunks are normal text chunks with `chunk_kind="table"`.
  - Near future: table rows can enter lexical/metadata lookup for exact code/table queries.
  - Vector indexing table rows is deferred until eval proves benefit.

- **Asset-text index**
  - Future: captions, nearby text, figure labels, and OCR-derived descriptions.
  - Should link to `asset_id` and source `chunk_id`.
  - Starts as text vector/lexical participation only; no visual vectors required.

- **OCR text index**
  - Future optional index, disabled by default per KB/profile.
  - Treat as asset-derived text unless the OCR layer is promoted into document elements.

- **Image vector index**
  - Future optional separate index, not mixed with text vector index.
  - Disabled by default; requires cost/latency limits and visual evidence eval.

## Object Participation Matrix

| Object | Text Vector | Lexical | Metadata/Facet | Graph | Asset Text | Visual Vector |
| --- | --- | --- | --- | --- | --- | --- |
| Child text chunk | Yes | Yes | Yes | Yes | No | No |
| Parent/context chunk | No by default | Optional later | Yes | No by default | No | No |
| Table chunk | Yes as text | Yes | Yes, `chunk_kind=table` | Yes | No | No |
| Table row | No initially | Future exact lookup | Future row metadata | No | No | No |
| Asset caption | Future yes | Future yes | Yes via `asset_id` | Linked, not node | Yes | No |
| OCR text | Future optional | Future optional | Yes via `asset_id` | Linked, not node | Yes | No |
| Image embedding | No | No | Yes via `asset_id` | Linked, not node | No | Future separate index |

## Qdrant Payload Schema Direction

Current safe payload keys should remain:

- `kb_name`
- `node_id`
- `build_id`
- `doc_id`
- `chunk_id`
- `chunk_identity_key`
- `manual_id`
- `source_file`
- `text_hash`

Future additive safe payload keys:

- `schema_version`
- `chunk_kind`
- `parser_profile`
- `parser_version`
- `page_start`
- `page_end`
- `section_path_hash` or low-cardinality section token, not raw long paths by default
- `asset_refs_hash` / `asset_count`, not raw URLs
- ACL-safe tenant/document permission keys when authorization requires them

Do not store:

- raw chunk text;
- raw query text;
- embeddings outside the vector field;
- absolute filesystem paths;
- secrets;
- signed URLs;
- large section path strings unless explicitly approved.

Point-id migration:

- Keep numeric `node_id` point ids until a dedicated index migration task.
- Store `chunk_id` in payload now so Phase 3 can reference stable ids.
- A future migration may use stable UUID/int64 point ids derived from `chunk_id`; it must support dual-read or full rebuild.

## Hybrid Fusion Strategy

### Default

Keep the current conservative pipeline:

1. Candidate generation from exact/in-memory vector or Qdrant ANN.
2. Lexical candidates/boosts where enabled.
3. Metadata narrowing/boosting.
4. Graph/WAVE propagation and deterministic rerank.

New score components should be added as explicit named components in debug before changing default ranking behavior.

### Explainable Fusion Exploration Plan

1. Baseline current pipeline.
2. Try simple normalized weighted score fusion with debug components.
3. Try reciprocal-rank fusion for independent candidate lists.
4. Compare against baseline on retrieval hit rate, table correctness, citation readiness, metadata narrowing, latency, and debuggability.
5. Consider learned fusion only after enough labeled eval/feedback data exists.

No learned fusion should become default without:

- stable eval fixtures;
- feedback-derived labels;
- latency budget;
- explainability story;
- fallback path.

## Incremental Rebuild Rules

| Change Type | Text Vector | Lexical | Metadata/Facet | Graph | Qdrant Payload | Future Asset/OCR |
| --- | --- | --- | --- | --- | --- | --- |
| Unchanged source + metadata | Reuse | Reuse/rebuild cheap | Reuse | Rebuild topology if current system requires | Refresh build payload only if needed | Reuse |
| Metadata-only update | Reuse embedding if text unchanged | Reuse text terms | Refresh | Rebuild graph if metadata edges/filters depend on it | Refresh payload | Reuse unless metadata affects assets |
| Parser profile change | Rebuild | Rebuild | Refresh | Rebuild | Full or safe point sync | Re-evaluate asset links |
| Chunker config/version change | Rebuild | Rebuild | Refresh | Rebuild | Full or safe point sync | Re-evaluate links |
| Table handling change | Rebuild table chunks | Rebuild table terms | Refresh `chunk_kind`/table facets | Rebuild | Full or safe point sync | N/A |
| Asset regeneration | Text chunks reusable | Reuse | Refresh asset refs/counts | Rebuild links if represented | Refresh payload hashes | Rebuild affected asset indexes |
| OCR regeneration | Reuse non-OCR chunks | Rebuild OCR terms | Refresh OCR facets | Rebuild links if represented | Refresh payload hashes | Rebuild OCR index |

Rule of thumb: reuse embeddings only when normalized chunk text and embedding config are unchanged. Refresh payloads when safe metadata changes even if vectors are reused.

## Debug and Observability Contract

Future `/retrieve` debug should expose safe, bounded fields:

- `schema_version`
- candidate counts by index
- selected index paths
- score components by opaque result id
- metadata narrowing decision summary
- graph propagation summary
- fallback reason
- index freshness/build id

Do not expose:

- raw query tokens;
- full matched snippets beyond user-facing evidence;
- raw vector values;
- large candidate id lists;
- unsafe source-file lists;
- secrets or signed URLs.

## Eval Gates For Future Index Changes

Every indexing/ranking implementation task must report:

- retrieval hit rate / MRR / recall;
- table retrieval correctness;
- metadata narrowing correctness;
- context/evidence readiness when Phase 3 exists;
- latency budget impact;
- failure fallback behavior;
- debug explainability.

## Follow-Up Implementation Tasks

1. Add index schema/version constants and safe payload docs/tests.
2. Add retrieval debug score-component scaffolding without changing ranking.
3. Add table-specific eval fixtures for table lookup queries.
4. Add Phase 3 `/retrieve` text evidence on top of existing child chunk indexes.
5. Later: parent context expansion after `/retrieve` exists.
6. Later: asset/OCR indexes after asset lifecycle and visual evidence are designed.
