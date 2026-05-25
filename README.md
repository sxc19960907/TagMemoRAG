# TagMemoRAG

A semantic retrieval engine for product manuals. The default path combines local vector scoring, metadata-aware filtering/boosting, bounded lexical recovery, optional Qdrant ANN candidate generation, and deterministic in-memory graph ranking. WAVE Phase 0/1 features remain available as experimental, default-off extensions; they are not part of the critical retrieval path unless explicitly enabled.

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

`build` indexes Markdown, plain text, and text-based PDF files (`.md`, `.txt`, `.pdf`). PDF support extracts embedded text and uses a parser profile to split section-like chunks when headings are visible; the default `product_manual` profile preserves current product-manual heading hints, while `generic` uses only structural heading cues plus optional `parser.pdf_heading_hints`. Scanned image-only PDFs still need OCR before indexing.

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
During build, manual metadata is also mirrored into a generic document contract (`doc_id`, `domain`, `doc_type`, `attributes`) plus internal identity tags such as `brand:gorenje`, `model:nrk6192`, `category:fridge`, `doc:gorenje-nrk6192-zh-cn-v1`, and `manual:gorenje-nrk6192-zh-cn-v1`. These internal tags help retrieval narrow or boost by document identity; `/manuals` and search results continue to expose only the original user-facing metadata tags.

Public web pages can be sampled into Markdown for general-knowledge RAG validation without committing fetched third-party content:

```bash
python -m tagmemorag knowledge sample-web \
  --url https://docs.python.org/3/tutorial/index.html \
  --output-dir .tmp/general-web-samples \
  --kb general_web \
  --domain software_docs \
  --doc-type documentation \
  --tag python

python -m tagmemorag build \
  --docs .tmp/general-web-samples/general_web \
  --kb general_web \
  --config config.yaml
```

Use `--preview` to fetch and parse pages without writing Markdown files. The sampler writes `.md` files plus sidecar metadata with `remote_id`, `url`, `domain`, and `doc_type` fields so public samples can feed the existing build and eval pipeline while remaining attributable.

### 2. Search from CLI

```bash
python -m tagmemorag search "蒸汽很小" --kb default --top-k 5
```

Use `--debug-search` to add low-cardinality operator diagnostics to the JSON output without changing default CLI responses.
When a query contains a known exact model, category alias, or brand, search can infer metadata narrowing before ranking. For example, `NRK6192 温度怎么调` hard-filters to chunks from the matching model when that model exists in the loaded KB. Explicit CLI/API filters always win over inferred filters, and empty inferred candidate sets fall back safely.

### 2.5. Try a local RAG answer demo

The offline demo uses the coffee-machine fixture, hashing embeddings, NPZ vector storage, and the noop answer provider. It does not require API keys, Qdrant, S3, or a running server.

```bash
bash scripts/seed_qa_demo.sh

python -m tagmemorag demo qa "蒸汽很小怎么办？" \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/qa-response.json
```

The JSON response includes the answer text, citation count, evidence count, bounded source metadata, `build_id`, `plan_id`, and warnings. The demo defaults to the top 2 evidence items for a cleaner first answer; pass `--top-k` to inspect more sources. The same payload is written to `--output` when provided.

To verify the managed-manual path that a normal user exercises, run the local library-to-QA smoke:

```bash
python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json
```

That command uploads the demo service manual into the managed library, performs an incremental rebuild, confirms the manual is searchable, then asks `服务模式怎么进入？`. A passing report has `status: "passed"`, `manual.searchable: true`, `manual.chunk_count` greater than zero, and a cited source ending in `demo/demo-service-manual.md`.

To try the same state through the browser:

```bash
python -m tagmemorag serve --config examples/config/qa-demo.yaml
```

Open `http://127.0.0.1:8000/admin/manual-library?kb_name=default` and confirm `demo-service-manual` is searchable with two chunks and no pending rebuild. Then open `http://127.0.0.1:8000/qa?kb_name=default`, ask `服务模式怎么进入？`, and confirm the answer mentions holding the clean and hot-water buttons for three seconds with `demo-service-manual.md` in the source list.

Filtered search narrows retrieval before local ranking and any enabled graph propagation:

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

Local readiness smoke check:

```bash
python -m tagmemorag readiness smoke
python -m tagmemorag readiness smoke --keep-workdir
```

The smoke command builds an isolated temporary KB with the offline hashing embedder, runs retrieve plus noop answer generation, verifies QueryPlan persistence, and round-trips a managed-library bundle. It is a local MVP composition check; it does not validate live traffic, Qdrant, S3, remote model providers, or multi-replica coordination.

For deployment profiles, backup/restore, Qdrant/S3 operations, diagnostics, and rollback playbooks, see [`docs/production-deployment-operations.md`](docs/production-deployment-operations.md). For the first production-like verification pass and retained evidence checklist, see [`docs/production-environment-verification.md`](docs/production-environment-verification.md).

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
Set request `debug: true` or `search.debug_metadata_enabled=true` to include a `debug` object with search strategy, ANN candidate/fallback details, lexical candidate/source counts, and effective search parameters. Diagnostics intentionally omit raw query text, extracted tokens, document text, vectors, trace/search ids, and candidate id lists.
Debug output also includes `debug.metadata_narrowing`, which reports detected metadata entities, inferred hard filters, soft boost filters, before/after candidate counts, and fallback reason. This is intended for operator routing diagnostics, not as a user-facing explanation.

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

M6 adds a file-backed library workflow under `manual_library.root_dir/{kb_name}`. The existing `GET /manuals` endpoint remains graph-derived for search-facing clients; `GET /manual-library?kb_name=...` lists uploaded or disabled manuals even before they have been rebuilt. Local sidecar mode remains the default.

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

`mode` can be `full`, `incremental`, or `auto`; the default remains `full` for compatibility. Incremental rebuilds use the dirty manual set in `.tagmemorag-library.json`, reuse unchanged chunks/vectors from the loaded KB, reuse unchanged chunk identities inside dirty manuals when `data/{kb}/chunk_identity.json` is compatible, parse/embed only new or changed dirty chunks, remove disabled/deleted dirty manuals, then rebuild graph topology globally before saving and swapping. `auto` chooses incremental only when dirty manual and estimated dirty chunk counts are within `manual_library.incremental_auto_max_dirty_manuals` and `manual_library.incremental_auto_max_dirty_chunks`; otherwise it performs a full rebuild and reports `auto_decision_reason`. If the old graph or dirty state is unavailable, the task falls back to a full rebuild by default and reports `requested_mode`, `effective_mode`, `dirty_manual_count`, `reused_chunk_count`, `embedded_chunk_count`, `fallback_reason`, `chunk_identity_fallback_reason`, `impact_summary`, `operations_summary`, and, for Qdrant-backed library rebuilds, `qdrant_sync`. Set `allow_fallback=false` to fail strict incremental requests instead.

Successful managed-library rebuilds write operational artifacts under `data/{kb}/`: `chunk_identity.json` for future chunk-level reuse and `rebuild_impact.json` for the latest non-textual added/removed/changed/reused/embedded counts. With `vector_store.provider=qdrant`, the impact and task metadata also include `qdrant_sync` counts for points upserted, deleted, and reused/skipped, plus any fallback reason. Export current dirty state with:

```bash
curl "http://127.0.0.1:8000/manual-library/dirty?kb_name=default&format=json" \
  -H "Authorization: Bearer tmr_live_..."

python -m tagmemorag manual-library dirty --kb default --format csv
```

The JSON dirty response is also the operator status view. It includes `pending_changes`, dirty manual rows with `searchable` and `exists`, `current_build_id`, `last_successful_build_id`, `last_impact_summary`, low-cardinality Qdrant sync counts, `recovery_actions`, and an `operations_summary`. The CSV format keeps the stable dirty-manual columns for compact operational exports.

#### Background rebuild queue

M28 adds an opt-in in-process queue for managed-library rebuilds. Keep it disabled for small local deployments that prefer immediate rebuild tasks. Enable it when uploads, bulk imports, object storage, embedding providers, or Qdrant can produce repeated or transient rebuild pressure:

```yaml
manual_library:
  rebuild_queue_enabled: true
  rebuild_queue_max_workers: 1
  rebuild_queue_max_attempts: 2
  rebuild_queue_retry_backoff_seconds: 5.0
  rebuild_queue_history_limit: 100
```

When enabled, `POST /manual-library/rebuild` returns a job payload instead of a low-level rebuild task. Requests for the same KB coalesce where safe: `full` upgrades queued `incremental` or `auto`, and `allow_fallback=false` stays strict. Different KBs may run concurrently up to `rebuild_queue_max_workers`; a single KB still runs one rebuild at a time.

```bash
curl -X POST http://127.0.0.1:8000/manual-library/rebuild \
  -H "Authorization: Bearer tmr_live_..." \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"default","mode":"auto","allow_fallback":true}'

curl "http://127.0.0.1:8000/manual-library/rebuild-jobs?kb_name=default" \
  -H "Authorization: Bearer tmr_live_..."

curl "http://127.0.0.1:8000/manual-library/rebuild-jobs/JOB_ID" \
  -H "Authorization: Bearer tmr_live_..."

curl -X POST "http://127.0.0.1:8000/manual-library/rebuild-jobs/JOB_ID/cancel" \
  -H "Authorization: Bearer tmr_live_..."
```

Queued jobs can be cancelled before they start. Running cancellation is cooperative at safe rebuild checkpoints; if the job has already passed the final save/swap point it may finish successfully while showing `cancel_requested=true`. Failed transient storage, embedding, and Qdrant-like failures retry up to `rebuild_queue_max_attempts`; invalid input/config errors fail without retry. The queue is process-local in M28, so after a server restart inspect dirty state and enqueue a fresh rebuild if needed. Roll back by setting `manual_library.rebuild_queue_enabled=false`, which restores immediate rebuild behavior.

#### SQLite registry and blob stores

M26 adds an opt-in registry/blob-store mode for managed manuals. It stores manual metadata, lifecycle state, versions, checksums, blob keys, and audit events in SQLite while storing original uploaded bytes through a blob-store boundary. M27 adds an S3-compatible implementation for MinIO, AWS S3, R2, OSS-compatible endpoints, and similar services. Local file mode remains the default:

```yaml
manual_library:
  registry_backend: file
  blob_backend: local
```

Enable local registry mode for a KB:

```yaml
manual_library:
  root_dir: product_manuals
  registry_backend: sqlite
  registry_path: data/manual_registry.sqlite3
  blob_backend: local
  blob_root_dir: data/manual_blobs
```

Migrate an existing sidecar library without moving or deleting source files:

```bash
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml --dry-run
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml
python -m tagmemorag manual-library registry verify-blobs --kb default --config config.yaml
python -m tagmemorag manual-library registry inspect --kb default --config config.yaml
```

Registry-backed rebuilds stage active records into a temporary sidecar tree and then run the existing parser/build path, so chunk metadata and dirty-state safety stay compatible. If staging or blob reads fail, the active graph is not swapped and pending state remains set. Rollback is config-only: switch `manual_library.registry_backend` back to `file` because migration leaves the original sidecars and source files in place.

Enable S3-compatible registry mode by installing the optional extra and configuring only bucket/endpoint metadata in YAML. Credentials are read from the environment variables named by config:

```bash
uv sync --extra s3
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin
```

```yaml
manual_library:
  root_dir: product_manuals
  registry_backend: sqlite
  registry_path: data/manual_registry.sqlite3
  blob_backend: s3
  s3_bucket: tagmemorag-manuals
  s3_prefix: manuals/dev
  s3_endpoint_url: http://localhost:9000
  s3_region: us-east-1
  s3_access_key_env: MINIO_ROOT_USER
  s3_secret_key_env: MINIO_ROOT_PASSWORD
  s3_addressing_style: path
```

For AWS S3 or compatible hosted services, leave `s3_endpoint_url` blank for AWS or set the provider endpoint URL, set `s3_bucket`, and either keep `s3_access_key_env` / `s3_secret_key_env` pointed at environment variables or set both names to empty strings to use boto3's default credential chain. Object keys are stored in the registry as safe relative keys, not signed URLs or credential-bearing strings.

Migration and verification use the same commands as local registry mode:

```bash
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml --dry-run
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml
python -m tagmemorag manual-library registry verify-blobs --kb default --config config.yaml
python -m tagmemorag manual-library rebuild --kb default --config config.yaml
```

If an S3 upload fails, registry rows and dirty state are not committed. If a rebuild cannot read an object, the previous graph keeps serving and dirty state remains pending. Roll back by restoring object-store availability and retrying; if you migrated from sidecars and kept local files, you can switch `registry_backend` back to `file` for an emergency rebuild path.

Portable import/export bundles:

```bash
python -m tagmemorag manual-library bundle export \
  --kb default \
  --config config.yaml \
  --output backups/default.bundle.zip

python -m tagmemorag manual-library bundle inspect \
  --bundle backups/default.bundle.zip \
  --config config.yaml \
  --target-kb restored

python -m tagmemorag manual-library bundle import \
  --bundle backups/default.bundle.zip \
  --config config.yaml \
  --target-kb restored \
  --dry-run

python -m tagmemorag manual-library bundle import \
  --bundle backups/default.bundle.zip \
  --config config.yaml \
  --target-kb restored \
  --conflict-mode fail
```

Bundles are ZIP archives with `tagmemorag-bundle.json`, `checksums.json`, per-manual metadata under `records/`, source bytes under `blobs/`, registry audit summaries when available, and dirty/rebuild diagnostic snapshots under `state/`. Inspect verifies safe archive paths, schema version, metadata shape, blob presence, and SHA-256 checksums without writing anything.

File-sidecar exports read only managed manuals that have valid sidecars. SQLite registry exports read original bytes through the configured `ManualBlobStore`, so S3-backed libraries produce self-contained local bundles instead of external S3 URLs. Bundle metadata stores safe logical blob keys for provenance only; it does not include credentials, signed URLs, request headers, absolute local paths, vectors, Qdrant dumps, stack traces, or raw search query text.

Import writes source bytes through the target deployment's configured backend: sidecar files in file mode, or blob store plus registry rows in SQLite mode. `--conflict-mode fail` aborts before writes on existing `manual_id` or `source_file` conflicts, `skip` imports only non-conflicting records, and `overwrite` replaces conflicting records. Imports mark the target KB dirty and pending rebuild but do not rebuild automatically, so the previous graph keeps serving until `manual-library rebuild` succeeds.

Disaster recovery sequence:

1. Export from the source deployment and store the bundle with normal backup controls.
2. On the target deployment, run `bundle inspect` with the target config and KB name.
3. Run `bundle import --dry-run` and review conflicts.
4. Run `bundle import` with the chosen conflict mode.
5. Run `manual-library dirty` to confirm pending state, then rebuild with `auto`, `incremental`, or `full`.

For local-to-object-storage migration, configure the target with `registry_backend=sqlite` and `blob_backend=s3`, inspect the bundle against that config, import, verify blobs, then rebuild. If import validation fails, no registry rows are written. If a later rebuild fails, fix the reported storage/Qdrant/embedding issue and retry; imported source bytes and dirty state remain available for recovery.

Rebuild recovery runbook:

1. Inspect pending state:

   ```bash
   python -m tagmemorag manual-library dirty --kb default --format json
   ```

2. For transient failures with `recovery_hint=retry_incremental`, rerun:

   ```bash
   python -m tagmemorag manual-library rebuild --kb default --mode incremental
   ```

3. If `chunk_identity_fallback_reason`, Qdrant uncertainty, or `recovery_hint=force_full_rebuild` appears, force a full rebuild:

   ```bash
   python -m tagmemorag manual-library rebuild --kb default --mode full
   ```

4. If Qdrant remains unavailable, switch the config to `vector_store.provider=npz`, restart/reload, and rebuild after Qdrant is restored.

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

The operations band at the top is the M29 diagnostics console. It calls `GET /manual-library/diagnostics?kb_name=...` and shows registry mode, blob backend, dirty manual counts, queue state, latest build/impact/Qdrant summaries, and recovery recommendations. In file-sidecar mode the registry card says the registry is disabled; that is a normal local/default state, not an error. In SQLite registry mode, use **Verify blobs** to run explicit blob reference checks before a rebuild, especially with S3-compatible storage. Missing blob rows show only manual ids, safe blob keys, and blob backend names.

When `manual_library.rebuild_queue_enabled=true`, rebuild/upload/bulk actions surface queued job ids and the queue panel can inspect, cancel active/queued/retrying jobs, or retry failed jobs. When queueing is disabled, the same rebuild button keeps the immediate `GET /rebuild/{task_id}` polling behavior. The audit timeline calls `GET /manual-library/registry/audit` and shows newest-first registry events for the selected manual or KB; file-sidecar mode returns an empty disabled timeline.

Safe recovery flows:

- Dirty state pending: inspect the dirty row list, retry `auto` or `incremental`, and use a full rebuild if fallback or identity compatibility is uncertain.
- Missing blobs: restore object-store/local blob availability, run **Verify blobs** again, then retry the queued job or trigger a full rebuild.
- Failed queue job: inspect the job error summary, retry if the failure is transient, or cancel superseded queued work before starting a higher-priority full rebuild.
- Qdrant uncertainty: restore Qdrant connectivity and prefer a full rebuild when the diagnostics show sync fallback or unknown sync state. Switching temporarily to local NPZ/file mode is a config rollback path, not an automatic UI action.

The JSON APIs above remain the canonical backend contract. If API key auth is enabled, paste a Bearer token into the page token field; the browser stores it only in `sessionStorage` for the current session.

### User Q&A page

Open the user-facing manual question-answer page at:

```text
http://127.0.0.1:8000/qa
```

The page calls `POST /qa/answer` with the user's question only. The backend
routes the question to an accessible loaded KB when it can, asks for
clarification when multiple manual contexts are plausible, and returns a
user-readable not-ready state when no KB is loaded. The page shows only the
answer, clarification/error states, and cited source snippets. It hides
debugging details such as plan ids, build ids, raw retrieval results, and
answerability internals; use the RAG workbench below when you need those.

For a fully local demo with deterministic offline answering:

```bash
scripts/seed_qa_demo.sh
python -m tagmemorag serve --config examples/config/qa-demo.yaml
```

Then open `/qa` and ask `蒸汽很小怎么办？`. The demo builds the `default` KB
from `tests/fixtures/coffee_machine.md` into `.tmp/tagmemorag-qa-demo/data`
and enables the deterministic extractive noop answer provider, so the page
returns an evidence-backed answer with cited source snippets without network
access or provider keys.

### RAG workbench

Open the question-answer workbench at:

```text
http://127.0.0.1:8000/admin/rag-workbench
```

Use `?kb_name=product-a` to preselect another KB. The workbench calls
`POST /answer` with `include_retrieve=true`, then shows the generated answer,
citations, warnings, plan/build ids, answerability, cited evidence, and top
retrieval results. Links in the top bar open the manual library and retrieval
quality pages for the same KB.

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
  lexical_enabled: true
  lexical_candidate_k: 32
  lexical_source_k: 3
  lexical_min_token_chars: 2
  lexical_boost: 0.2
  lexical_exact_code_boost: 0.15
  lexical_model_boost: 0.12
  metadata_narrowing_enabled: true
  metadata_narrowing_brand_policy: boost_if_not_unique      # boost_if_not_unique | hard_filter | boost
  metadata_narrowing_category_policy: hard_filter_product_manual # hard_filter_product_manual | hard_filter | boost
  metadata_narrowing_min_candidates: 1
  debug_metadata_enabled: false
  ann_preselect_enabled: false
  ann_candidate_k: 64
  ann_force_exact_on_filters: false

parser:
  max_chars: 500
  min_chars: 50
  pdf_profile: product_manual   # product_manual | generic
  pdf_heading_hints: []          # extra PDF heading hints for non-default profiles

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

### Config Profiles And Validation

Example profiles live under `examples/config/`:

- `local-hashing-npz.yaml`
- `local-sqlite-registry.yaml`
- `qdrant.yaml`
- `s3-blob.yaml`
- `answer-openai-compatible.yaml`

Validate a profile before starting the service:

```bash
python -m tagmemorag config validate --config examples/config/local-hashing-npz.yaml
```

`config validate` is static and local: it loads the config with normal env precedence, checks local writable paths, checks required env var names for configured remote providers, and warns when optional extras such as `qdrant-client` or `boto3` are not importable. It does not call Qdrant, S3, embedding, reranker, answer, OCR, or visual providers.

Live provider probes are explicit because they can call external services:

```bash
python -m tagmemorag provider probe --config examples/config/answer-openai-compatible.yaml --answer
python -m tagmemorag provider probe --config examples/config/qdrant.yaml --qdrant
python -m tagmemorag provider probe --config config.yaml --all
```

Probe output is JSON and bounded: it reports provider status, env var names, dependency/provider names, and high-level error types, but not secrets, Authorization headers, raw responses, generated answer text, vectors, or document text.

Use the checks for different questions:

| Check | Answers |
| --- | --- |
| `config validate` | Is this config coherent and locally satisfiable? |
| `provider probe` | Do explicitly selected remote providers respond with the configured credentials/endpoints? |
| `readiness smoke` | Do the deterministic MVP build/retrieve/answer/queryplan/bundle paths compose in this checkout? |
| `pilot run` | Do the local config/probe/readiness/answer-quality/eval pilot checks compose into one retained rollout report? |
| `/ready` | Is this running process ready to serve its loaded KB? |

For a bounded pre-pilot gate and retained JSON/Markdown report, see [Production Pilot Runbook](docs/production-pilot-runbook.md):

```bash
python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --answer-quality-suite tests/fixtures/answer_quality/basic.jsonl \
  --hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --workdir .tmp/production-pilot \
  --output .tmp/production-pilot/report.json
```

### Qdrant Vector Backend

The default vector backend is local NPZ at `data/{kb_name}/vectors.npz`. Qdrant is optional: it persists vectors externally while graph topology, anchors, chunk identity, rebuild impact, and build metadata remain local under `data/{kb_name}/`.

Install the optional client extra and start a local Qdrant for development:

```bash
uv sync --extra qdrant
docker run -p 6333:6333 qdrant/qdrant
```

The optional `qdrant-client` extra is supported on Python `<3.13` while the project pins `numpy<2`.

Enable Qdrant in `config.yaml`:

```yaml
vector_store:
  provider: qdrant
  qdrant_url: http://localhost:6333
  collection_prefix: tagmemorag
  timeout_seconds: 10
```

Environment overrides use the normal nested form:

```bash
export TAGMEMORAG__VECTOR_STORE__PROVIDER=qdrant
export TAGMEMORAG__VECTOR_STORE__QDRANT_URL=http://localhost:6333
export TAGMEMORAG__VECTOR_STORE__COLLECTION_PREFIX=tagmemorag
```

Each KB uses a collection named `{collection_prefix}_{kb_name}` after safe character normalization. Examples:

| Prefix | KB | Collection |
|--------|----|------------|
| `tagmemorag` | `default` | `tagmemorag_default` |
| `tagmemorag` | `product/a` | `tagmemorag_product-a` |
| `tmr-prod` | `zh_CN manuals` | `tmr-prod_zh_CN-manuals` |

Qdrant points use graph `node_id` as point id. New points store safe payload fields only: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`. Unsafe fields include raw chunk text, source document bodies, embedding arrays outside the point vector, API keys, environment secrets, arbitrary metadata dumps, and high-cardinality diagnostic blobs. Existing collections with only legacy `kb_name`/`node_id` payloads remain loadable because `load_kb()` retrieves by graph node id and still fails clearly if a graph node is missing a vector.

During successful managed-library rebuilds, Qdrant collections are synced before graph/meta artifacts are swapped. The sync order is:

1. upsert new or changed points
2. refresh safe payloads for reused incremental points
3. delete stale old point ids

Full sync upserts all current graph points and then deletes stale old node ids. Safe incremental sync uses compatible `chunk_identity.json` data to skip unchanged vectors, refresh reused payloads in batches when the client supports it, upsert only new/changed node ids, and delete stale ids after required upserts succeed. If identity/impact data is missing or unsafe, the rebuild falls back to `strategy=full_sync` and reports `fallback_reason` in `qdrant_sync`. If Qdrant sync fails, the old loaded graph remains active, dirty library state stays pending, and stale deletes are not attempted before current point upserts succeed.

Use the read-only inspection command to check the configured collection, local graph count, Qdrant point count, missing graph vectors, payload key coverage, and the last low-cardinality Qdrant sync summary:

```bash
python -m tagmemorag qdrant inspect --kb default --config config.yaml
```

The JSON report is intentionally bounded. It includes counts, collection name, safe payload key names, capped missing node id samples, and recommendations. It does not print raw vectors, raw chunk text, full payload values, secrets, or unbounded point id lists.

Common operator workflow:

```bash
# 1. Check pending manual-library state and recovery hints.
python -m tagmemorag manual-library dirty --kb default --config config.yaml --format json

# 2. Inspect graph/vector consistency for the Qdrant collection.
python -m tagmemorag qdrant inspect --kb default --config config.yaml

# 3. Retry the normal incremental path when dirty state is valid.
python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode incremental

# 4. Force a full Qdrant refresh if vectors or payloads have diverged.
python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode full
```

If Qdrant remains unavailable, roll back to local NPZ by setting `vector_store.provider=npz` and rebuilding the KB so `data/{kb_name}/vectors.npz` is regenerated:

```bash
export TAGMEMORAG__VECTOR_STORE__PROVIDER=npz
python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode full
```

Troubleshooting guide:

| Symptom | Check | Safe action |
|---------|-------|-------------|
| `collection_exists=false` | Qdrant URL, collection name, service health | Start Qdrant, verify config, then run full rebuild |
| `missing_vector_count>0` | `qdrant inspect` missing count/sample | Retry incremental rebuild; force full rebuild if it persists |
| Legacy payload coverage only has `kb_name`/`node_id` | `sample_payload_keys`, `payload_key_coverage` | No immediate outage; next full or compatible incremental rebuild refreshes safe payloads |
| Dirty state remains pending after rebuild failure | `manual-library dirty --format json` | Fix Qdrant reachability, retry incremental, or full rebuild |
| Qdrant outage blocks startup/load | provider config | Temporarily switch to `npz` and rebuild from managed sources |

TagMemoRAG also adds a lightweight local lexical signal before final ranking. It scans already-loaded node fields, including chunk text, headers, paths, source files, manual metadata, and tags, to recover exact product-manual terms such as `E21`, `E-21`, `F07`, `HR6FDFF701SW`, `排水泵`, and `童锁`. Lexical matches add bounded seed nodes and a bounded score hint; they do not replace vector similarity, graph propagation when enabled, anchors, filters, or metadata/tag boosts. Disable it with `search.lexical_enabled=false`, or tune the bounded scan with `search.lexical_candidate_k`, `search.lexical_source_k`, `search.lexical_boost`, `search.lexical_exact_code_boost`, and `search.lexical_model_boost`.

Metadata narrowing runs just before filtering and ranking. It builds a local index from loaded graph metadata, detects high-confidence product-manual identity signals, and resolves them into hard filters or boost-only filters according to config. Exact model matches hard-filter by default, category aliases such as `冰箱`/`refrigerator` hard-filter in product-manual KBs, and brand-only matches boost unless the KB contains a single brand or policy says otherwise. Disable with `search.metadata_narrowing_enabled=false` for A/B checks or broad exploratory retrieval.

Qdrant can also act as an optional ANN candidate generator for search. Set `search.ann_preselect_enabled=true` to let TagMemoRAG ask Qdrant for up to `search.ann_candidate_k` candidate node ids before local ranking runs. This does not replace local ranking: TagMemoRAG still recomputes exact local vector scores, unions safe lexical candidates when enabled, and applies deterministic in-memory graph propagation according to the active config, so ANN only narrows the candidate set and does not become the final ranker.

The ANN path is intentionally conservative:

- exact local search remains the default
- NPZ-backed KBs always stay on the exact path
- filters are still enforced locally
- lexical candidates respect the same local filters and KB boundary
- eligible anchor nodes are force-included in the ANN candidate set
- if Qdrant ANN fails, returns invalid ids, or yields no safe filtered candidate set, search falls back to exact local scoring

If you want filtered searches to bypass ANN entirely, set `search.ann_force_exact_on_filters=true`.

### HTTP Embedding Providers

TagMemoRAG can call OpenAI-compatible embedding APIs instead of loading a local model. This works with providers such as SiliconFlow:

```yaml
model:
  provider: http
  base_url: https://api.siliconflow.cn/v1
  api_key_env: SILICONFLOW_API_KEY
  name: Qwen/Qwen3-Embedding-8B
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

Use `tests/fixtures/eval/coffee.jsonl` as the fast smoke suite for basic CLI and report compatibility. Use the broader product-manual suite when checking retrieval behavior across categories, metadata, tags, ANN preselection, and rebuild-related regressions:

```bash
uv run tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --output .tmp/eval-product-report.json \
  --eval-data-dir .tmp/eval/product-manuals
```

The product-manual suite includes lexical-sensitive cases for short Chinese terms, punctuation variants, fault codes, and model-like identifiers. To reproduce the M25 check with deterministic offline embeddings:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m25-product-post \
  --output .tmp/eval/m25-reports/product-post.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

Use the general web suite to validate non-manual public documentation. It is not
part of the default fixture-only CI gate because the corpus is seeded from live
public URLs into `.tmp`:

```bash
scripts/seed_general_web_eval.sh

.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8 \
  --min-recall-at-k 0.75 \
  --min-mrr 0.4 \
  --min-hit-at-k 0.75
```

Pair it with the generic documentation answer-quality diagnostic:

```bash
.venv/bin/python -m tagmemorag eval answer-quality \
  --suite tests/fixtures/answer_quality/general_web.jsonl
```

To run the live seeded retrieval output through the local extractive answer
generator and answer-quality checks:

```bash
.venv/bin/python scripts/diag_general_web_answer_eval.py \
  --docs .tmp/general-web-eval/general_web \
  --suite tests/fixtures/eval/general_web.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web
```

The general web baseline covers real public pages across multiple domains:
Python and GitHub software documentation (`domain=software_docs`), MDN HTTP
caching documentation (`domain=web_platform_docs`), and USAGov/IRS public
service help articles (`domain=public_service`). The GitHub repository case
models multi-evidence retrieval explicitly: the repository/folder definition and
the README/Markdown explanation may be returned as separate chunks. The MDN and
IRS cases likewise include complementary evidence so answer-quality checks see
more than a single easy snippet.

Before shipping a reranking or evidence-usefulness change, compare baseline and
candidate retained reports with the offline reranking evaluation gate:

```bash
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/rerank-batch-release-readiness.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/rerank-batch-ranking-pressure.json \
  --format markdown
```

The gate fails if release readiness is no longer `passed`, if general-web
hit/recall/MRR regresses, if ranking pressure gets worse, or if tracked GitHub
pressure cases move later. Its output is bounded to metrics and checked-in case
ids; do not commit generated `.tmp` reports.

Use the multi-format real-knowledge suite to validate format diversity with
real public sources. It materializes HTML-derived Markdown, a text-based public
PDF, and DOCX-derived Markdown under `.tmp` before running the normal build and
eval pipeline:

```bash
.venv/bin/python scripts/seed_multiformat_real_knowledge.py \
  --output-dir .tmp/multiformat-real-knowledge \
  --kb multiformat_real

.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl \
  --docs .tmp/multiformat-real-knowledge/multiformat_real \
  --config examples/config/local-hashing-npz.yaml \
  --kb multiformat_real \
  --top-k 8 \
  --min-recall-at-k 0.0 \
  --min-mrr 0.0 \
  --min-hit-at-k 0.0

.venv/bin/python scripts/diag_multiformat_answer_eval.py \
  --docs .tmp/multiformat-real-knowledge/multiformat_real \
  --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb multiformat_real \
  --top-k 8
```

The committed suite stores source URLs and expected evidence only. Downloaded
PDF/DOCX files and converted Markdown remain runtime artifacts.

Use the mixed-domain diagnostic to validate that real manuals and public docs
can coexist in one shared KB without obvious top-ranked cross-domain pollution:

```bash
scripts/seed_general_web_eval.sh

.venv/bin/python scripts/diag_mixed_domain_eval.py \
  --stage-from-defaults \
  --suite tests/fixtures/eval/mixed_knowledge.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb mixed_knowledge
```

`--stage-from-defaults` copies real PDFs from `product_manuals/` and seeded
public docs from `.tmp/general-web-eval/general_web` into a temporary mixed
corpus. The suite uses one shared `kb_name` plus positive and negative
expectations, so it catches both missed evidence and wrong-domain top results.

For retrieval tuning, compare one bounded parameter change at a time and keep the JSON reports. `eval run` accepts search-parameter overrides for experiments without editing `config.yaml`:

```bash
uv run tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --output .tmp/eval-product-source4.json \
  --eval-data-dir .tmp/eval/product-source4 \
  --source-k 4 \
  --min-recall-at-k 0 \
  --min-mrr 0 \
  --min-hit-at-k 0
```

Supported tuning overrides are `--top-k`, `--source-k`, `--steps`, `--decay`, `--amplitude-cutoff`, `--aggregate`, `--metadata-field-boost`, and `--tag-boost`. The report `config_snapshot.search` records the effective values. M23 evaluated source count, propagation depth, decay, aggregate mode, and metadata/tag boost variants against the coffee and product-manual fixtures; the product baseline was already at `recall_at_k=1.0`, `mrr=1.0`, and `hit_at_k=1.0`, so the default search settings remain unchanged. `aggregate=sum` regressed product-manual recall and should not be used as a default without new evidence.

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

Expected results can match by `source_file`, `header`, `anchor_key`, `text_contains`, and `metadata`; all supplied fields must match. The report includes per-case `precision_at_k`, `recall_at_k`, `mrr`, `hit_at_k`, expected references, actual top-k results, and the low-cardinality search strategy summary used by the same execution path as API and CLI search. Default gate thresholds apply to `recall_at_k`, `mrr`, and `hit_at_k`; `precision_at_k` is reported and only becomes a hard gate when `--min-precision-at-k` is set.

## Docker Deployment

```bash
docker build -t tagmemorag:latest .
docker compose up
```

The container runs as a non-root user, logs JSON to stdout, prepackages the default BGE model, and sets `HF_HUB_OFFLINE=1` so runtime startup does not depend on external network access. Mount `./data:/app/data` for KB persistence.

If the build environment cannot reach Hugging Face reliably, pass a compatible mirror endpoint while building:

```bash
docker build --build-arg HF_ENDPOINT=https://hf-mirror.com -t tagmemorag:latest .
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

## Quality CI

`.github/workflows/quality.yml` runs on every PR and push to `master`. It runs the unit + e2e tests and then walks every JSON Lines suite under `tests/fixtures/eval/` with the hashing embedder, comparing each suite's `precision_at_k / recall_at_k / mrr / hit_at_k` against `tests/fixtures/eval/baselines/hashing.json`. Suite thresholds are derived as `max(baseline - 0.02, case-level minimum)`.

Reproduce CI locally:

```bash
uv sync --extra dev
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
uv run python scripts/run_eval_ci.py
```

Refresh the baseline (after deliberate quality changes):

```bash
uv run python scripts/build_eval_baseline.py \
  --embedder hashing \
  --output tests/fixtures/eval/baselines/hashing.json
```

For a SiliconFlow run with the production target model (`Qwen/Qwen3-Embedding-8B`, 4096 dim), set `SILICONFLOW_API_KEY` and run `scripts/eval-siliconflow.sh`. The script wraps `build_eval_baseline.py --embedder siliconflow` (with smoke test, exponential-backoff retry, and atomic write). To diff against hashing in one shot, append `--compare-with tests/fixtures/eval/baselines/hashing.json`:

```bash
uv run python scripts/build_eval_baseline.py \
  --embedder siliconflow \
  --output tests/fixtures/eval/baselines/siliconflow.json \
  --compare-with tests/fixtures/eval/baselines/hashing.json
```

`tests/fixtures/eval/baselines/siliconflow.json` is **informational only** — it captures the production embedder's measurements but is **not** a CI quality gate. Today's eval fixtures' case-level thresholds were authored against hashing-embedder-recall, so siliconflow rankings often miss the same case-level cuts; `run_eval_ci.py --baseline siliconflow.json --embedder siliconflow --no-default-thresholds` is the closest you get to a self-pass run, but case-level fixture thresholds are not bypassable. Diagnosing or reauthoring the fixture suite to match the production embedder is a separate readiness task.

Generate the offline reauthoring queue before editing fixture expectations:

```bash
uv run python scripts/diagnose_eval_reauthoring.py --format markdown
```

The report compares hashing vs SiliconFlow aggregate baselines and marks suites as `ok`, `monitor`, `reauthor`, or `investigate`. It does not call external providers, rewrite JSONL fixtures, or make SiliconFlow a CI gate.

For the next level down, summarize a saved eval report into a bounded case-review table:

```bash
uv run python scripts/summarize_eval_case_review.py \
  --report .tmp/eval-review/coffee.json \
  --format markdown
```

By default the case summary redacts raw queries and snippets. Use `--include-query` only for local review when that content is acceptable.

## Tag Data Model

TagMemoRAG persists `manual.metadata.tags` into a structured, position-aware SQLite layer alongside the existing `manual_records` table, plus a global EPA basis file. Search behavior is unchanged at this layer — these tables are populated for downstream analytics and ranking experiments.

### SQLite tables (in `data/manual_registry.sqlite3`)

- `tags(id, kb_name, name, vector BLOB, embedding_dim, embedded_at, UNIQUE(kb_name, name))` — canonical tag entities with embeddings filled by the rebuild pipeline.
- `manual_tags(kb_name, manual_id, tag_id, position INTEGER, PK(kb_name, manual_id, tag_id))` — link rows recording the 1-indexed position of each tag inside `metadata.tags`. Tag order matters; see [docs/tag-ordering-convention.md](docs/tag-ordering-convention.md).
- `tag_intrinsic_residuals(tag_id PK, residual_energy REAL DEFAULT 1.0, neighbor_count INTEGER DEFAULT 0, computed_at TEXT)` — placeholder table populated by future residual analysis; default `1.0` keeps downstream formulas neutral.

All three tables use `CREATE TABLE IF NOT EXISTS`, so old `manual_registry.sqlite3` databases upgrade in place. `FOREIGN KEY ... ON DELETE CASCADE` removes link/residual rows when a tag is deleted.

### Global EPA basis (`data/_global/epa_basis.npz`)

A KB-independent orthonormal basis trained over canonical tag embeddings. Stored fields: `orthoBasis`, `basisMean`, `basisEnergies`, `basisLabels`, `K`, `dim`, `train_kind`, `tag_count_at_train`, `trained_at`, `schema_version`.

- **Cold-start**: when `len(canonical_tags) < K*2`, the basis is the first `K` rows of an identity matrix (`train_kind="cold-start"`). This keeps small KBs working without a degenerate PCA fit.
- **Real PCA**: once the canonical-tag corpus crosses `K*2`, the basis is rebuilt from KMeans centroids fed into `sklearn.decomposition.PCA` (`train_kind="real-pca"`).
- **Concurrency**: a `data/_global/epa_basis.lock` file (`fcntl.flock`) serializes retrains across concurrent KB rebuilds. `data/_global/epa_basis.dirty` flags pending retrains triggered by tag rewrites or manual deletes.
- **CLI**: `python -m tagmemorag epa rebuild [--force]` triggers a manual full retrain.

### Observability

The rebuild task response (`GET /rebuild/{task_id}`) gains the following fields:

- `tag_embeddings_added`, `tag_embeddings_skipped`, `tag_embeddings_failed`, `tag_embedding_error`
- `orphan_tags_removed`
- `epa_basis_train_kind`, `epa_basis_K`, `epa_basis_tag_count`, `epa_train_error`

Prometheus metrics (`/metrics`):

- `tagmemorag_tag_embeddings_total{kb_name, outcome}` — counts of tag embedding outcomes (`added`/`skipped`/`failed`).
- `tagmemorag_tags_total{kb_name}` — current canonical tag count.
- `tagmemorag_epa_basis_retrain_total{outcome}` — retrain events grouped by `cold-start`/`real-pca`/`skipped`/`failed`.
- `tagmemorag_epa_basis_retrain_duration_seconds{outcome}` — retrain latency histogram.

### Emergency rollback

`config.yaml` has a `wave_phase0` section with two kill switches:

```yaml
wave_phase0:
  enabled: true
  epa_basis_enabled: true
```

Setting either to `false` disables the EPA basis path without removing the SQLite tables. To fully revert the data layer:

```bash
sqlite3 data/manual_registry.sqlite3 \
  "DROP TABLE IF EXISTS manual_tags; DROP TABLE IF EXISTS tag_intrinsic_residuals; DROP TABLE IF EXISTS tags;"
rm -rf data/_global/
```

The next rebuild recreates everything; `execute_search` output is byte-identical regardless of whether the data is present.

### Experimental WAVE Phase 1 — co-occurrence + spike propagation

Phase 1 turns tag data into a query-vector enhancement. Each rebuild now also writes a directed co-occurrence matrix at `data/_global/tag_cooccurrence/{kb}.npz`, and an opt-in spike walk over that matrix can fuse a "tag context vector" into the query before vector search runs. **This is experimental and defaults to off** so existing deployments keep current behaviour.

```yaml
wave_phase1:
  enabled: true                # master switch (rebuild + search)
  spike_enabled: false         # query-vector enhancement — flip to true to activate
  cooccurrence_enabled: true   # rebuild step on/off
  legacy_chunk_tag_boost: false  # escape hatch: keep chunk-side tag bonus when spike is on
```

Relationship to existing knobs:
- `search.tag_boost = 0.03` keeps its numeric value. With `spike_enabled=true`, it is consumed as the base alpha for the query-vector blend; the chunk-side `tags`-field bonus inside `wave_searcher` is silenced unless `legacy_chunk_tag_boost=true`.
- Setting `spike_enabled=false` returns the search path to Phase 0 byte-for-byte.
- `rm -rf data/_global/tag_cooccurrence/` is safe — the loader returns `None` on missing files and `apply_tag_boost` short-circuits.

EPA dynamic boost remains opt-in. Keep `dynamic_boost_factor_strategy: constant`
until `data/_global/epa_basis.npz` reports `train_kind="real-pca"`; with the
default `wave_phase0.epa_min_k=8`, that means at least 16 canonical tags. Before
switching to `dynamic_boost_factor_strategy: epa`, run
`uv run python scripts/diag_epa_logic_depth.py` and confirm the real-PCA alpha
distribution passes. The Phase 2a hashing fixture uses
`epa_logic_depth_scale: 2.0` and `epa_floor: 0.0`; if EPA mode looks noisy in a
deployment, switch the strategy back to `constant`.

Phase 2b-1 adds a third option `dynamic_boost_factor_strategy: pyramid`. It
swaps the top-K cosine seed selector for a multi-level Gram-Schmidt residual
pyramid (V6 source `applyTagBoost`'s `[2] Residual Pyramid` step) and uses the
full source formula:

```
activation_mult = act_min + tag_memo_activation * (act_max - act_min)
dynamic = (logicDepth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activation_mult
        * pyramid_post_scale     # then floored at epa_floor
```

`resonance` stays stubbed at `0` (Phase 2b-2 territory). Defaults
(`pyramid_post_scale=4.0` calibrated on hashing dim=64 fixture, `act_min=0.5`,
`act_max=1.5`) are wired to keep alpha series within the same magnitude as the
`epa` path. To switch: confirm
`uv run python scripts/diag_pyramid_dynamic_boost.py` returns
`overall: PASS`, then set `dynamic_boost_factor_strategy: pyramid`. Roll back to
`epa` or `constant` if hashing-dim noise dominates `coherence`; alternatively
set `pyramid_use_handshake_features: false` to disable the handshake submodule
without removing pyramid (degenerates `tag_memo_activation` to 0, equivalent to
`act_mult = act_min`).

Full design, tuning notes, and the 2026-05-17 KEEP_OFF readiness result live in [`docs/wave-phase1-architecture.md`](docs/wave-phase1-architecture.md).

#### External modulators (Phase 2b-2)

When `dynamic_boost_factor_strategy: pyramid` is on, the search request can pass
two extra "spotlight" hints that map to V6 `applyTagBoost`'s 4 peripheral
modulators (langPenalty + dynamicCoreBoostFactor + core completion + ghost
injection). All inputs are optional and default off; under `constant`/`epa`
strategies they round-trip through `info` without changing weights (`R10`).

`SearchRequest` adds:

```jsonc
{
  "core_tags": ["filter-cleaning", "cooling"],   // synonym-resolved to canonical
  "ghost_tags": [
    {"name": "airflow", "vector": [0.12, ...], "is_core": true},
    {"name": "noise",   "vector": [0.04, ...], "is_core": false}
  ]
}
```

- **`core_tags`**: caller already knows the query's key tag(s). The matcher first
  resolves synonyms (e.g. `cooling-mode → cooling`) via `tag_governance`, then
  forces those tags into the candidate set under `strategy="pyramid"`. If a
  named tag is present in the KB but missed by the pyramid pass, it is pulled
  via SQL and weighted at `max_base × dynamicCoreBoostFactor`.
- **`ghost_tags`**: caller has KB-external tags with vectors (e.g. expansion
  tags from another model). Vector dim must match the embedding model;
  mismatched ghosts are silently skipped and counted in
  `info.ghost_skipped_dim_mismatch`. Hard ghosts (`is_core=true`) get the
  dynamic core-boost multiplier; soft ghosts use unit weight.
- **`wave_phase1.lang_penalty_enabled` (default `false`)**: turn on to
  re-introduce V6's "tag is technical noise in non-technical world" penalty.
  Defaults preserve hashing-fixture invariance because the cold-start EPA basis
  emits axis labels like `axis-0` / `cooling`, which match the technical-world
  regex and thus never fire the penalty. Once a real-PCA basis surfaces a
  non-technical label (e.g. a Politics-themed cluster), enabling the flag will
  start dampening pure-ASCII technical tags.

Example:

```bash
curl -s -X POST http://localhost:8000/search \
  -H 'content-type: application/json' \
  -d '{
    "question": "F07 sensor wire loose",
    "kb_name": "default",
    "core_tags": ["filter-cleaning"],
    "ghost_tags": [
      {"name": "airflow", "vector": [0.1, 0.2, 0.0, ...], "is_core": true}
    ]
  }'
```

`info.tag_boost` in the debug payload now includes
`core_tags_input / core_tags_resolved / core_completion_count / ghosts_injected
/ ghost_skipped_dim_mismatch / lang_penalty_applied_count / query_world` for
post-mortem diagnostics.

#### Cross-domain resonance (Phase 3)

Phase 3 replaces the Phase 2b-1 `resonance = 0` stub with a port of V6
`EPAModule.detectCrossDomainResonance` (source: `lioensky/VCPToolBox`
`EPAModule.js:170-201`). When `wave_phase1.cross_domain_resonance_enabled`
is `true`, the dynamicBoostFactor formula's resonance term becomes
`log(1 + Σ sqrt(top.energy * sec.energy))` over each EPA dominant axis pair
that crosses the hardcoded threshold `0.15`.

Defaults are off so 8 hashing eval suites stay byte-stable. Toggle per-deploy:

```yaml
wave_phase1:
  spike_enabled: true
  dynamic_boost_factor_strategy: pyramid
  cross_domain_resonance_enabled: true   # Phase 3 opt-in
```

**Log-domain amplification reference:**

| `resonance` | `log(1 + r)` | dynamic factor multiplier |
|------------:|------------:|--------------------------:|
| 0 (cold-start / single dominant axis) | 0.000 | × 1.00 |
| 0.3 (one moderate co-activation)      | 0.262 | × 1.26 |
| 0.5 (one strong co-activation)        | 0.405 | × 1.40 |
| 1.0 (one strong + several moderate)   | 0.693 | × 1.69 |
| 2.0 (multi-axis dense activation)     | 1.099 | × 2.10 |

The 12-tag hashing fixture diagnostic (`scripts/diag_pyramid_dynamic_boost.py`)
records `pyramid+resonance` `resonance: mean=0.76, std=0.12, range=[0.47, 1.05]`
on the eval set with the default `pyramid_post_scale=4.0` (no recalibration
needed); the alpha series clears the D2 PASS thresholds with margin.

The debug payload exposes the per-bridge breakdown only when at least one pair
crosses the threshold:

```json
{
  "tag_boost": {"cross_domain_resonance": 0.5, "cross_domain_bridges_count": 1, ...},
  "tag_boost_debug": {
    "cross_domain_bridges": [
      {"from": "Tech", "to": "Logic", "strength": 0.5, "balance": 1.0}
    ]
  }
}
```

Phase 3.5 will train real `tag_intrinsic_residuals` and feed them into the
ResidualPyramid as a prior; Phase 4 covers V8 `geodesicRerank`.

#### Experimental geodesic rerank (Phase 4)

Phase 4 ports V8 `TagMemoEngine.geodesicRerank` as an experimental, default-off WAVE extension. After Phase 1 spike
propagation publishes a tag-energy field (`accumulated_energy`), V8 reranks
the wave_search candidates by mean tag energy per chunk:

```yaml
wave_phase1:
  spike_enabled: true
  geodesic_rerank_enabled: true       # Phase 4 opt-in
  geodesic_alpha: 0.3                 # blend weight, clamped to [0, 1]
  geodesic_oversample_factor: 2.0     # pool = top_k × factor
  geodesic_min_geo_samples: 2         # source default 4; lowered for ~3 tags/chunk
```

Default off keeps existing baselines byte-stable. The 2026-05-17 readiness check kept this flag OFF after mixed eval results. When on, V8 silently
no-ops if any precondition fails (spike disabled, matrix missing, energy
field empty, etc.) and records the reason via
`tagmemorag_geodesic_rerank_skipped_total{reason}` for ops dashboards.
Diagnostics live in `scripts/diag_geodesic_rerank.py` (sweeps α and
min_geo_samples, prints hit-count histogram, applies a PASS gate of
`applied_pct > 0` AND `max_geo_zero_pct < 50`). Full design notes are in
[`docs/wave-phase1-architecture.md`](docs/wave-phase1-architecture.md#geodesic-rerank-phase-4).

## Roadmap

| Milestone | Scope |
|-----------|-------|
| **M0** ✅ | Wave algorithm, anchors, JSON+NPZ storage, FastAPI, CLI, zero-downtime rebuild |
| **M1** ✅ | Dockerfile, JSON logs, `/health`+`/ready`, graceful shutdown, env-var config |
| **M2** ✅ | API key + rate limiting, multi-KB isolation, query cache |
| **M3** ✅ | Eval harness (precision@k / MRR), CI regression gate |
| **M4** ✅ | Prometheus metrics, OpenTelemetry traces |
| **M5** ✅ | Manual metadata sidecars, filters, facets, tag-aware search boosts |
| **M6** ✅ | File-backed managed manual library, upload/update/disable/delete, library rebuild |
| **M7** ✅ | Server-rendered manual library admin UI |
| **M8** ✅ | Deterministic tag suggestion API and admin UI workflow |
| **M9** ✅ | Qdrant vector backend as selectable vector persistence |
| **M10** ✅ | Batch import/validation and production manual library ergonomics |
| **M11** ✅ | Tag governance, synonym mapping, and usage analytics |
| **M12** ✅ | Retrieval quality feedback loop and eval dataset growth |
| **M13** ✅ | Incremental manual rebuild/update path |
| **M14** ✅ | Incremental rebuild strategy and impact reporting |
| **M15** ✅ | Point-level incremental Qdrant updates |
| **M16** ✅ | Qdrant ANN preselection as candidate generation before local deterministic ranking |
| **M17** ✅ | Incremental rebuild plus ANN integration regression coverage |
| **M18** ✅ | Batched Qdrant payload refresh with safe per-point fallback |
| **M19** ✅ | Opt-in search diagnostics and operator debug metadata |
| **M20** ✅ | Expanded retrieval quality fixtures and product-manual eval coverage |
| **M21** ✅ | Rebuild operations UX and failure recovery guidance |
| **M22** ✅ | Qdrant operations documentation and inspection command |
| **M23** ✅ | Retrieval tuning experiment loop; defaults preserved from eval evidence |
| **M25** ✅ | Hybrid lexical retrieval for exact fault codes, model terms, and short product-manual phrases |
| **M26** ✅ | SQLite manual registry, lifecycle audit, and local blob-store boundary |
| **M27** ✅ | S3-compatible manual blob store behind registry-backed libraries |
| **M28** ✅ | Opt-in background rebuild queue and cancellation controls |
| **M29** ✅ | Admin diagnostics for dirty state, registry, blobs, audit, and queue jobs |
| **M30** ✅ | Portable managed-library import/export bundles |
| **M31** ✅ | Tag data model: position-aware tag links, embeddings, and global EPA basis |
| **Ops Guide** ✅ | Production deployment and operations guide for Docker, backups, Qdrant, S3, diagnostics, and rollback |
| **Parking lot** | Payload-filtered ANN, HA multi-replica, streaming bundle API, bundle encryption/signing |
