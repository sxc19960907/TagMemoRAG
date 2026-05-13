# TagMemoRAG

A production-grade semantic retrieval engine for product manuals, built on the **WAVE-RAG** algorithm: knowledge chunks are organized into a semantic topology graph, and user queries propagate as waves along graph edges — interference peaks become the top-K results.

`kb_name` selects an isolated knowledge base under `data/{kb_name}/`. API keys can be scoped to one or more KBs.

## Install

```bash
# with uv (recommended)
uv sync --extra dev

# or pip
pip install -e ".[dev]"
```

## Quick Start

### 1. Build a knowledge base

```bash
python -m tagmemorag build --docs docs/ --kb default --config config.yaml
```

`build` indexes Markdown, plain text, and text-based PDF files (`.md`, `.txt`, `.pdf`). PDF support extracts embedded text; scanned image-only PDFs need OCR before indexing.

Manual metadata can live next to each source file as `<manual>.metadata.json`:

```json
{
  "manual_id": "gorenje-nrk6192-zh-cn-v1",
  "title": "Gorenje NRK6192 refrigerator manual",
  "source_file": "fridge/gorenje-nrk6192.zh-CN.v1.pdf",
  "brand": "Gorenje",
  "product_category": "fridge",
  "product_name": "NRK6192",
  "product_model": "NRK6192",
  "language": "zh-CN",
  "version": "v1",
  "tags": ["temperature-setting", "troubleshooting"]
}
```

If no sidecar exists, TagMemoRAG creates fallback metadata from the relative path, filename, parent directory, and `language="unknown"`.

### 2. Search from CLI

```bash
python -m tagmemorag search "蒸汽很小" --kb default --top-k 5
```

Filtered search narrows retrieval before WAVE propagation:

```bash
python -m tagmemorag search "冰箱温度怎么调" \
  --kb fridge \
  --category fridge \
  --model NRK6192 \
  --language zh-CN \
  --tag temperature-setting
```

### 3. Start the API server

```bash
python -m tagmemorag serve --host 127.0.0.1 --port 8000
```

Health probes:

```bash
curl http://127.0.0.1:8000/health  # 200 ok when the process is alive
curl http://127.0.0.1:8000/ready   # 200 only after model warm-up and KB load
```

## API Reference

### `POST /search`

```json
{
  "question": "蒸汽很小",
  "top_k": 5,
  "steps": 3,
  "decay": 0.7,
  "aggregate": "max",
  "kb_name": "default",
  "filters": {
    "product_category": "fridge",
    "product_model": "NRK6192",
    "language": "zh-CN",
    "tags": ["temperature-setting"]
  }
}
```

Response includes `build_id`, `search_time_ms`, and a `results` array. Each result has the existing `node_id / score / text / header / path / source_file / anchor_key` fields plus manual metadata such as `manual_id`, `manual_title`, `brand`, `product_category`, `product_model`, `language`, `version`, and `tags`.
The response also includes `cache: "hit" | "miss"`.

### `POST /rebuild`

Triggers an async rebuild from `docs_dir`. Returns `202 {task_id, status}` immediately; poll `GET /rebuild/{task_id}` for completion. Old graph keeps serving during rebuild (zero-downtime double-buffer swap).

### Anchor management

| Endpoint | Description |
|----------|-------------|
| `POST /anchor` | Set anchor: `{node_id, label, boost, propagation_boost}` |
| `DELETE /anchor/{anchor_key}` | Remove anchor |
| `GET /anchor` | List all anchors + unresolved |

Anchors survive rebuilds via stable `anchor_key` (sha256 of path+header+text prefix). Unresolved anchors are returned in the rebuild response.

### `GET /graph_info`

Returns node/edge counts, `build_id`, `meta`, and any `unresolved_anchors`.

### `GET /manuals`

Returns the manuals discovered in a loaded KB plus available metadata facets for UI filters:

```json
{
  "kb_name": "fridge",
  "build_id": "202605...",
  "manuals": [
    {
      "manual_id": "gorenje-nrk6192-zh-cn-v1",
      "title": "Gorenje NRK6192 refrigerator manual",
      "product_category": "fridge",
      "product_model": "NRK6192",
      "language": "zh-CN",
      "tags": ["temperature-setting"],
      "chunk_count": 12
    }
  ],
  "facets": {
    "brand": ["Gorenje"],
    "product_category": ["fridge"],
    "product_model": ["NRK6192"],
    "language": ["zh-CN"],
    "tags": ["temperature-setting"]
  }
}
```

### Managed manual library

M6 adds a file-backed library workflow under `manual_library.root_dir/{kb_name}`. The existing `GET /manuals` endpoint remains graph-derived for search-facing clients; `GET /manual-library?kb_name=...` lists uploaded or disabled manuals even before they have been rebuilt.

Validate metadata without writing files:

```bash
curl -X POST http://127.0.0.1:8000/manuals/validate \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","metadata":{"manual_id":"cm1","title":"CM1 Manual","source_file":"coffee/cm1.md","product_category":"coffee","tags":["Maintenance Task"]}}'
```

Upload or overwrite a manual with multipart form data:

```bash
curl -X POST http://127.0.0.1:8000/manuals \
  -H "Authorization: Bearer tmr_live_..." \
  -F kb_name=default \
  -F overwrite=false \
  -F metadata='{"manual_id":"cm1","title":"CM1 Manual","source_file":"coffee/cm1.md","product_category":"coffee","language":"zh-CN","tags":["maintenance"]}' \
  -F file=@product_manuals/default/coffee/cm1.md
```

Metadata/file changes mark the KB as `rebuild_required` but do not change the currently served graph. Rebuild the managed library with:

```bash
curl -X POST http://127.0.0.1:8000/manual-library/rebuild \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","mode":"incremental"}'
```

`mode` can be `full`, `incremental`, or `auto`; the default remains `full` for compatibility. Incremental rebuilds use the dirty manual set in `.tagmemorag-library.json`, reuse unchanged chunks/vectors from the loaded KB, reuse unchanged chunk identities inside dirty manuals when `data/{kb}/chunk_identity.json` is compatible, parse/embed only new or changed dirty chunks, remove disabled/deleted dirty manuals, then rebuild graph topology globally before saving and swapping. `auto` chooses incremental only when dirty manual and estimated dirty chunk counts are within `manual_library.incremental_auto_max_dirty_manuals` and `manual_library.incremental_auto_max_dirty_chunks`; otherwise it performs a full rebuild and reports `auto_decision_reason`. If the old graph or dirty state is unavailable, the task falls back to a full rebuild by default and reports `requested_mode`, `effective_mode`, `dirty_manual_count`, `reused_chunk_count`, `embedded_chunk_count`, `fallback_reason`, `chunk_identity_fallback_reason`, `impact_summary`, and, for Qdrant-backed library rebuilds, `qdrant_sync`. Set `allow_fallback=false` to fail strict incremental requests instead.

Successful managed-library rebuilds write operational artifacts under `data/{kb}/`: `chunk_identity.json` for future chunk-level reuse and `rebuild_impact.json` for the latest non-textual added/removed/changed/reused/embedded counts. With `vector_store.provider=qdrant`, the impact and task metadata also include `qdrant_sync` counts for points upserted, deleted, and reused/skipped, plus any fallback reason. Export current dirty state with:

```bash
curl "http://127.0.0.1:8000/manual-library/dirty?kb_name=default&format=json" \
  -H "Authorization: Bearer tmr_live_..."

python -m tagmemorag manual-library dirty --kb default --format csv
```

Other library operations:

| Endpoint | Description |
|----------|-------------|
| `PATCH /manuals/{manual_id}/metadata` | Update sidecar metadata |
| `PUT /manuals/{manual_id}/file` | Replace the source document |
| `DELETE /manuals/{manual_id}?kb_name=...` | Disable a manual for future rebuilds |
| `DELETE /manuals/{manual_id}?kb_name=...&hard=true` | Hard delete source + sidecar; requires `admin` |
| `POST /manual-library/bulk/preview` | Validate JSON/JSONL/CSV metadata and uploaded documents without writing |
| `POST /manual-library/bulk/import` | Re-run preview and import selected valid rows |
| `GET /manual-library/dirty` | Export current dirty manual state as JSON or CSV |
| `GET /manual-library/tags` | Return governed tag facets, counts, and drift issues |
| `PUT /manual-library/tags/policy` | Save `.tagmemorag-tags.json`; requires `rebuild` |
| `POST /manual-library/tags/rewrite/preview` | Preview tag merge/rename without writing |
| `POST /manual-library/tags/rewrite` | Commit tag merge/rename and mark rebuild pending |

Create/update/disable/rebuild require the `rebuild` scope plus KB allowlist access. Hard delete also requires `admin`. `status=disabled` or `status=archived` sidecars are skipped by future builds while remaining visible in the managed library list.

Tag governance is optional and file-backed per KB at `manual_library.root_dir/{kb_name}/.tagmemorag-tags.json`:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "policy_mode": "advisory",
  "canonical_tags": [
    {"tag": "maintenance", "label": "Maintenance", "description": "Cleaning and routine care"}
  ],
  "synonyms": {
    "cleaning": "maintenance",
    "clean": "maintenance"
  },
  "deprecated_tags": {
    "maintainance": {"replacement": "maintenance", "reason": "Misspelling"}
  }
}
```

When policy exists, validation and bulk preview warn on synonyms, deprecated tags, and unknown tags; `policy_mode=strict` turns unknown/deprecated tags into errors. Suggestions prefer canonical tags, and search filters accept synonyms by resolving them at the API/CLI boundary. Existing sidecars are never rewritten by validation or search. Use rewrite preview first, then commit:

```bash
curl -X POST http://127.0.0.1:8000/manual-library/tags/rewrite/preview \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","source_tags":["cleaning"],"target_tag":"maintenance","mode":"merge"}'

curl -X POST http://127.0.0.1:8000/manual-library/tags/rewrite \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","source_tags":["cleaning"],"target_tag":"maintenance","mode":"merge","update_policy":true}'
```

CLI helpers use the same service layer:

```bash
python -m tagmemorag tag stats --kb default
python -m tagmemorag tag policy --kb default --file tag-policy.json
python -m tagmemorag tag rewrite-preview --kb default --source-tag cleaning --target-tag maintenance
python -m tagmemorag tag rewrite --kb default --source-tag cleaning --target-tag maintenance --update-policy
```

Tag drift means the library and policy disagree, or the currently loaded graph no longer matches sidecars. After a successful rewrite, rebuild the managed library before relying on tag filters in search.

Bulk import accepts metadata as JSON array, JSONL, or CSV. Recommended CSV columns:

```csv
manual_id,title,source_file,brand,product_category,product_name,product_model,language,version,tags,status,notes
cm1,CM1 Manual,coffee/cm1.md,Acme,coffee,CM1,CM1,zh-CN,v1,"maintenance, steam-wand",active,
```

Preview first, then import. Preview rows include `manual_id`, `source_file`, `tag`, `status`, `action`, `severity`, and a message. `action` is one of `create`, `update`, `skip`, `conflict`, or `invalid`; `severity=error` rows cannot be imported.

```bash
curl -X POST http://127.0.0.1:8000/manual-library/bulk/preview \
  -H "Authorization: Bearer tmr_live_..." \
  -F kb_name=default \
  -F metadata_format=csv \
  -F metadata_file=@manuals.csv \
  -F files=@product_manuals/default/coffee/cm1.md

curl -X POST http://127.0.0.1:8000/manual-library/bulk/import \
  -H "Authorization: Bearer tmr_live_..." \
  -F kb_name=default \
  -F metadata_format=csv \
  -F metadata_file=@manuals.csv \
  -F mode=create_only \
  -F selected_rows='[2]' \
  -F files=@product_manuals/default/coffee/cm1.md
```

The same backend service is available through thin CLI helpers:

```bash
python -m tagmemorag manual-bulk preview --metadata manuals.csv --metadata-format csv --file product_manuals/default/coffee/cm1.md
python -m tagmemorag manual-bulk import --metadata manuals.csv --metadata-format csv --file product_manuals/default/coffee/cm1.md --selected-row 2
python -m tagmemorag manual-library rebuild --kb default --mode incremental
```

Use `mode=create_only` to reject existing `manual_id` or `source_file`. Use `mode=upsert` with `overwrite=true` for explicit updates. Use `mode=dry_run` for preview-only checks. Bulk imports mark the library as pending rebuild but do not make changes searchable until `POST /manual-library/rebuild` succeeds.

Suggest tags for an upload or edit draft without writing files:

```bash
curl -X POST http://127.0.0.1:8000/manuals/tags/suggest \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","metadata":{"manual_id":"cm1","title":"CM1 Coffee Machine Maintenance Manual","source_file":"coffee/cm1-maintenance.md","product_category":"coffee","product_model":"CM1","tags":["steam-wand"]},"limit":8}'
```

The endpoint requires the `search` scope and returns normalized, scored suggestions with source hints and short reasons. M8 suggestions are deterministic heuristics from draft metadata, filename/path signals, and tags/facets already present in the selected KB; they are not LLM-generated or authoritative taxonomy. Accepting suggestions only changes the draft tags field in the UI. Metadata is not persisted until the existing upload or save action succeeds, and `POST /manuals/validate` remains the canonical normalization check.

### Manual library admin UI

Start the same FastAPI service, then open:

```text
http://127.0.0.1:8000/admin/manual-library
```

Use `?kb_name=product-a` to preselect another KB. The page is a server-rendered Jinja2 shell with static CSS and small vanilla JavaScript; it does not add a Node or SPA build step. The UI lists managed manuals, filters by text/status/searchable/rebuild state, validates metadata, suggests optional tags, uploads manuals, previews/imports bulk CSV/JSON/JSONL batches, edits sidecars, replaces source files, disables or hard deletes manuals, opens tag governance facets/drift/policy/rewrite controls, and triggers/polls managed library rebuilds.

The JSON APIs above remain the canonical backend contract. If API key auth is enabled, paste a Bearer token into the page token field; the browser stores it only in `sessionStorage` for the current session.

### Retrieval quality feedback

Search responses include `trace_id` and `search_id` so clients can attach bounded feedback to a specific retrieval interaction. Feedback is stored per KB at `storage.data_dir/{kb_name}/feedback/search-feedback.jsonl`; review state lives in `search-feedback-reviews.json`.

Submit feedback with the `search` scope:

```bash
curl -X POST http://127.0.0.1:8000/search/feedback \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","trace_id":"...","search_id":"...","build_id":"...","query":"E05 蒸汽异常怎么处理","outcome":"missing_result","expected":[{"source_file":"coffee_machine.md","header":"E05 蒸汽异常","metadata":{"manual_id":"coffee-machine"}}],"note":"Expected the E05 troubleshooting section."}'
```

Operators use `admin` scope to list, review, preview promotion, and export eval drafts:

```bash
curl "http://127.0.0.1:8000/search/feedback?kb_name=default&status=new" \
  -H "Authorization: Bearer tmr_live_..."

curl -X PATCH http://127.0.0.1:8000/search/feedback/FB_ID \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","status":"triaged","operator_note":"Good eval candidate."}'

curl -X POST http://127.0.0.1:8000/search/feedback/promote/preview \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","feedback_ids":["FB_ID"]}'
```

The same workflow is available from the CLI and always prints JSON:

```bash
python -m tagmemorag feedback submit --kb default --json feedback.json
python -m tagmemorag feedback list --kb default --status new
python -m tagmemorag feedback review --kb default --feedback-id FB_ID --status triaged
python -m tagmemorag feedback promote-preview --kb default --feedback-id FB_ID
python -m tagmemorag feedback promote --kb default --feedback-id FB_ID --output eval_drafts/default/feedback.jsonl --append
```

The operator UI is available at:

```text
http://127.0.0.1:8000/admin/retrieval-quality
```

Promotion writes JSONL cases in the existing eval schema. Existing draft files are not overwritten unless `append` or `overwrite` is explicit.

### Authentication

Enable API key auth in `config.yaml` and send keys as Bearer tokens:

```bash
python -m tagmemorag auth generate-key --id cs-a --scopes search --kb product-a --rate 200

curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"question":"蒸汽很小","kb_name":"product-a"}'
```

Missing or invalid credentials return `401 UNAUTHORIZED`; valid keys without the required scope or KB access return `403 FORBIDDEN`. `/health`, `/ready`, `/metrics`, and API docs remain public by default.

### Rate Limiting

Rate limits are enforced per API key in process memory. Responses include:

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
```

Exceeded limits return `429 RATE_LIMITED` with `Retry-After`.

### Multi-KB

Build multiple KBs by using different `--kb` names:

```bash
python -m tagmemorag build --docs docs/product-a --kb product-a
python -m tagmemorag build --docs docs/product-b --kb product-b
```

`GET /kb` lists the KBs visible to the current API key, including `build_id`, `node_count`, `anchors_version`, and `status`.

### Query Cache

`/search` uses an in-memory LRU+TTL cache when `cache.enabled=true`. The cache key includes `kb_name`, `build_id`, `anchors_version`, normalized question text, and all search parameters, so rebuilds and anchor edits naturally miss stale entries. Admins can clear it:

```bash
curl -X POST http://127.0.0.1:8000/admin/cache/clear \
  -H "Authorization: Bearer tmr_live_admin..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"product-a"}'
```

## Configuration

`config.yaml` (all fields optional, shown with defaults):

```yaml
model:
  name: BAAI/bge-small-zh-v1.5   # use "hashing" for offline/test mode
  device: cpu
  batch_size: 32

graph:
  sim_threshold: 0.5
  parent_child_bonus: 0.2
  sibling_bonus: 0.1
  consecutive_bonus: 0.15

search:
  top_k: 5
  source_k: 3
  steps: 3
  decay: 0.7
  amplitude_cutoff: 0.01
  aggregate: max          # max | sum
  metadata_field_boost: 0.05
  tag_boost: 0.03
  ann_preselect_enabled: false
  ann_candidate_k: 64
  ann_force_exact_on_filters: false

anchor:
  default_boost: 2.0
  default_propagation_boost: 1.0   # >1.0 enables in-propagation amplification
  reconcile_threshold: 0.85

storage:
  data_dir: ./data
  schema_version: "1"

vector_store:
  provider: npz              # npz | qdrant
  qdrant_url: http://localhost:6333
  collection_prefix: tagmemorag
  timeout_seconds: 10

server:
  host: 0.0.0.0
  port: 8000
  shutdown_timeout_seconds: 60

logging:
  level: INFO
  format: json        # json | console

auth:
  enabled: false
  backend: config
  public_paths: [/health, /ready, /docs, /redoc, /openapi.json]
  global_max_rate_limit_per_minute: 1000
  keys:
    - id: cs-a
      hash: sha256:...
      label: Customer service A
      kb_allowlist: [product-a]
      scopes: [search]
      rate_limit_per_minute: 200

rate_limit:
  enabled: true
  default_per_minute: 60
  window_seconds: 60

cache:
  enabled: true
  max_entries: 10000
  ttl_seconds: 3600

manual_library:
  root_dir: product_manuals
  allow_overwrite: false

observability:
  metrics:
    enabled: true
    path: /metrics
    include_runtime: true
  tracing:
    enabled: false
    service_name: tagmemorag
    otlp_endpoint:
    sample_ratio: 1.0
    export_timeout_seconds: 5
```

Environment variables override YAML and defaults. Use the `TAGMEMORAG__` prefix and double underscores for nested fields:

| Variable | Example |
|----------|---------|
| `TAGMEMORAG__SERVER__PORT` | `9000` |
| `TAGMEMORAG__LOGGING__LEVEL` | `DEBUG` |
| `TAGMEMORAG__MODEL__NAME` | `BAAI/bge-small-zh-v1.5` |
| `TAGMEMORAG__STORAGE__DATA_DIR` | `/app/data` |
| `TAGMEMORAG__VECTOR_STORE__PROVIDER` | `qdrant` |
| `TAGMEMORAG__AUTH__ENABLED` | `true` |
| `TAGMEMORAG__CACHE__MAX_ENTRIES` | `20000` |
| `TAGMEMORAG__OBSERVABILITY__TRACING__ENABLED` | `true` |
| `TAGMEMORAG__OBSERVABILITY__TRACING__OTLP_ENDPOINT` | `http://otel-collector:4317` |

### Qdrant Vector Backend

The default vector backend is local NPZ at `data/{kb_name}/vectors.npz`. To persist vectors in Qdrant while keeping graph, anchors, and build metadata in local JSON files, install the optional extra and point the service at Qdrant:

```bash
uv sync --extra qdrant
docker run -p 6333:6333 qdrant/qdrant
```

```yaml
vector_store:
  provider: qdrant
  qdrant_url: http://localhost:6333
  collection_prefix: tagmemorag
```

Each KB uses a collection named `{collection_prefix}_{kb_name}` after safe character normalization. Qdrant is currently used as vector persistence; WAVE-RAG still loads the KB's vectors back into memory for graph propagation during search. New points store safe payload fields only: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`; raw chunk text, vectors beyond the point vector, and secrets are not stored in payloads. Existing collections with only `kb_name`/`node_id` payloads remain loadable because `load_kb()` retrieves by graph node id and still fails clearly if a graph node is missing a vector.

During successful managed-library rebuilds, Qdrant collections are synced before graph/meta artifacts are swapped. Full sync upserts all current graph points and then deletes stale old node ids. Safe incremental sync uses compatible `chunk_identity.json` data to skip unchanged points, upsert only new/changed node ids, and delete stale ids after required upserts succeed. If identity/impact data is missing or unsafe, the rebuild falls back to `strategy=full_sync` and reports `fallback_reason` in `qdrant_sync`. If Qdrant sync fails, the old loaded graph remains active, dirty library state stays pending, and stale deletes are not attempted before current point upserts succeed. Operators can roll back to local NPZ by setting `vector_store.provider=npz`, or force a full Qdrant cleanup by running a managed-library rebuild with `mode=full`.

Qdrant can also act as an optional ANN candidate generator for search. Set `search.ann_preselect_enabled=true` to let TagMemoRAG ask Qdrant for up to `search.ann_candidate_k` candidate node ids before local WAVE-RAG runs. This does not replace WAVE-RAG ranking: TagMemoRAG still recomputes exact local vector scores and runs graph propagation in memory, so ANN only narrows the candidate set and does not become the final ranker.

The ANN path is intentionally conservative:

- exact local search remains the default
- NPZ-backed KBs always stay on the exact path
- filters are still enforced locally
- eligible anchor nodes are force-included in the ANN candidate set
- if Qdrant ANN fails, returns invalid ids, or yields no safe filtered candidate set, search falls back to exact local scoring

If you want filtered searches to bypass ANN entirely, set `search.ann_force_exact_on_filters=true`.

The optional `qdrant-client` extra is supported on Python `<3.13` while the project pins `numpy<2`.

### HTTP Embedding Providers

TagMemoRAG can call OpenAI-compatible embedding APIs instead of loading a local model. This works with providers such as SiliconFlow:

```yaml
model:
  provider: http
  base_url: https://api.siliconflow.cn/v1
  api_key_env: SILICONFLOW_API_KEY
  name: Qwen/Qwen3-VL-Embedding-8B
  dim: 4096
  dimensions: 4096
  batch_size: 32
  timeout_seconds: 30
  normalize: true
```

The API key is read only from the environment named by `api_key_env`:

```bash
export SILICONFLOW_API_KEY=...
```

The HTTP backend sends `POST {base_url}/embeddings` with `{model, input, encoding_format: "float"}`. If your provider exposes a full custom endpoint, set `model.embeddings_url` instead of `base_url`.

## Observability

Prometheus metrics are enabled by default:

```bash
curl http://127.0.0.1:8000/metrics | grep tagmemorag
```

Example scrape config:

```yaml
scrape_configs:
  - job_name: tagmemorag
    static_configs:
      - targets: ["tagmemorag:8000"]
```

Custom metrics include HTTP request volume/latency, search cache hit/miss, result counts, cache operations, rate-limit decisions, rebuild lifecycle, loaded KB count, embedder readiness, and embedding latency/failures. Labels are intentionally low-cardinality: route template, method, status code, `kb_name`, cache status, operation, outcome, and stable error code. Metrics never label raw query text, trace IDs, task IDs, API keys, document paths/text, or vectors.

Useful PromQL examples:

```promql
sum(rate(tagmemorag_search_requests_total[5m])) by (kb_name, cache_status, outcome)
histogram_quantile(0.95, sum(rate(tagmemorag_search_duration_seconds_bucket[5m])) by (le, kb_name))
sum(rate(tagmemorag_rate_limit_checks_total{outcome="limited"}[5m]))
tagmemorag_rebuilds_in_progress
tagmemorag_embedder_ready
```

OpenTelemetry tracing is disabled by default. Enable it with an OTLP collector:

```bash
export TAGMEMORAG__OBSERVABILITY__TRACING__ENABLED=true
export TAGMEMORAG__OBSERVABILITY__TRACING__OTLP_ENDPOINT=http://otel-collector:4317
export TAGMEMORAG__OBSERVABILITY__TRACING__SAMPLE_RATIO=0.1
```

HTTP requests get automatic FastAPI spans when tracing is enabled. Business spans cover search cache lookup, query embedding, WAVE search, rebuild, KB load/build, and cache clear. `X-Trace-Id` is still returned in every API response and appears in logs as `trace_id`; traces include it as `tagmemorag.x_trace_id` so logs, API responses, and distributed traces can be correlated.

## Quality Eval

Run the offline retrieval regression suite with the deterministic hashing embedder:

```bash
uv run tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --output .tmp/eval-report.json \
  --eval-data-dir .tmp/eval/coffee
```

For CI, use a config whose model provider is `hashing` so the gate does not download a model or call the network:

```yaml
model:
  provider: hashing
  dim: 64
```

By default, docs-based eval builds into `--eval-data-dir` and leaves normal `storage.data_dir` untouched. Use `--reuse-built-kb` only when you intentionally want to evaluate an already persisted KB.

Eval suites are JSONL: one query case per line. Each case names the KB, query, and one or more expected relevant chunks:

```json
{"id":"coffee-steam-weak","kb_name":"default","query":"蒸汽很小怎么办","relevant":[{"source_file":"coffee_machine.md","header":"蒸汽功能","text_contains":["蒸汽很小","喷嘴"]}]}
```

Expected results can match by `source_file`, `header`, `anchor_key`, and `text_contains`; all supplied fields must match. The report includes per-case `precision_at_k`, `recall_at_k`, `mrr`, `hit_at_k`, expected references, and actual top-k results. Default gate thresholds apply to `recall_at_k`, `mrr`, and `hit_at_k`; `precision_at_k` is reported and only becomes a hard gate when `--min-precision-at-k` is set.

## Docker Deployment

```bash
docker build -t tagmemorag:m1 .
docker compose up
```

The container runs as a non-root user, logs JSON to stdout, prepackages the default BGE model, and sets `HF_HUB_OFFLINE=1` so runtime startup does not depend on external network access. Mount `./data:/app/data` for KB persistence.

If the build environment cannot reach Hugging Face reliably, pass a compatible mirror endpoint while building:

```bash
docker build --build-arg HF_ENDPOINT=https://hf-mirror.com -t tagmemorag:m1 .
```

Compose uses `/health` for liveness so an empty first boot is still healthy. For Kubernetes, use `/ready` for readiness:

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet: { path: /ready, port: 8000 }
  initialDelaySeconds: 10
  periodSeconds: 5
startupProbe:
  httpGet: { path: /ready, port: 8000 }
  periodSeconds: 5
  failureThreshold: 24
terminationGracePeriodSeconds: 60
```

## Running Tests

```bash
uv run pytest tests/ -v
```

Uses `HashingEmbedder` (no HF download required) for all unit and E2E tests.

## Roadmap

| Milestone | Scope |
|-----------|-------|
| **M0** ✅ | Wave algorithm, anchors, JSON+NPZ storage, FastAPI, CLI, zero-downtime rebuild |
| **M1** | Dockerfile, JSON logs, `/health`+`/ready`, graceful shutdown, env-var config |
| **M2** | API key + rate limiting, multi-KB isolation, query cache |
| **M3** | Eval harness (precision@k / MRR), CI regression gate |
| **M4** | Prometheus metrics, OpenTelemetry traces |
| **M5** | Manual metadata sidecars, filters, facets, tag-aware search boosts |
| **M6** | File-backed managed manual library, upload/update/disable/delete, library rebuild |
| **M7** | Server-rendered manual library admin UI |
| **M8** | Deterministic tag suggestion API and admin UI workflow |
| **M9** | Qdrant vector backend as selectable vector persistence |
| **M10** | Batch import/validation and production manual library ergonomics |
| **M11** | Tag governance, synonym mapping, and usage analytics |
| **M12** | Retrieval quality feedback loop and eval dataset growth |
| **M13** | Incremental manual rebuild/update path |
| **post-v1** | Qdrant ANN preselection, HA multi-replica, additional vector backends |
