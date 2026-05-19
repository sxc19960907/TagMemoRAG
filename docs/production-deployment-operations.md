# Production Deployment And Operations

This guide is the operator runbook for deploying TagMemoRAG with the surfaces that exist today: Docker Compose, local NPZ vectors, optional Qdrant vectors, SQLite manual registry, local or S3-compatible manual blobs, process-local rebuild queue, admin diagnostics, and portable import/export bundles.

It is intentionally honest about limits. TagMemoRAG is currently shaped for single-machine or single-writer deployments. It does not provide built-in leader election, durable distributed queues, automatic object-store backup, automatic Qdrant backup, bundle encryption/signing, or transparent multi-replica write coordination.

## Deployment Profiles

| Profile | Config shape | Durable state | When to use |
| --- | --- | --- | --- |
| Local file + NPZ | `manual_library.registry_backend=file`, `vector_store.provider=npz` | `data/`, `product_manuals/`, `config.yaml`, secrets/env | Small local or single-node deployments. |
| File + Qdrant | `registry_backend=file`, `vector_store.provider=qdrant` | Local files plus Qdrant collection `{collection_prefix}_{kb}` or generation-specific collection | Larger vector sets where Qdrant is useful as vector storage or ANN preselection. |
| SQLite registry + local blobs | `registry_backend=sqlite`, `blob_backend=local` | SQLite registry, local blob directory, generated data artifacts | Multi-operator manual management on one node. |
| SQLite registry + S3 blobs | `registry_backend=sqlite`, `blob_backend=s3` | SQLite registry plus external S3-compatible bucket | Deployments where original manuals must live in object storage. |

Keep local file/NPZ mode as the recovery baseline unless your deployment requires object storage or Qdrant. Optional services should be introduced one at a time, with backup and rollback tested before production traffic depends on them.

## Docker Compose Baseline

The included `docker-compose.yml` runs one `tagmemorag` service with:

- image build from `Dockerfile`
- environment from `.env.example`
- `TAGMEMORAG__STORAGE__DATA_DIR=/app/data`
- bind mount `./data:/app/data`
- read-only container root filesystem and `/tmp` as tmpfs
- `GET /health` healthcheck
- 60 second stop grace period

Start the baseline:

```bash
cp .env.example .env
docker compose --env-file .env up --build
```

Check process and readiness:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/metrics | head
```

`/health` only proves the process can answer. `/ready` is the traffic gate: it returns success only after model warm-up and KB load. A first boot with no built KB can be healthy but not ready.

Run the local MVP smoke check before deploys or after upgrades:

```bash
python -m tagmemorag readiness smoke
python -m tagmemorag readiness smoke --keep-workdir
```

This command creates an isolated temporary workspace, uses deterministic local providers, builds a tiny KB, exercises retrieve plus noop answer generation, verifies QueryPlan persistence, and round-trips a managed-library bundle. Treat it as a local composition check. It does not prove live API reachability, remote embedding/reranker/LLM provider health, Qdrant/S3 availability, production data quality, or multi-replica write safety.

The Compose file also has a `sqlite` tools profile for inspecting `data/manual_registry.sqlite3`:

```bash
docker compose --profile tools run --rm sqlite ".tables"
```

Do not run multiple write-capable app containers against the same local `data/` and SQLite registry unless you have an external single-writer discipline. The app does not coordinate writes across replicas.

## Configuration And Secrets

Configuration precedence is:

```text
environment > .env > YAML config > defaults
```

Use double-underscore environment keys, for example:

```bash
TAGMEMORAG__SERVER__PORT=8000
TAGMEMORAG__STORAGE__DATA_DIR=/app/data
TAGMEMORAG__VECTOR_STORE__PROVIDER=qdrant
TAGMEMORAG__VECTOR_STORE__QDRANT_URL=http://qdrant:6333
```

Keep secrets out of YAML. Provider keys are read from environment variables named by config fields, for example `model.api_key_env`, `reranker.api_key_env`, `answer.api_key_env`, and S3 credential env names.

Example HTTP embedding posture:

```bash
export SILICONFLOW_API_KEY=...
export TAGMEMORAG__MODEL__PROVIDER=http
export TAGMEMORAG__MODEL__NAME=Qwen/Qwen3-Embedding-8B
export TAGMEMORAG__MODEL__DIMENSIONS=4096
```

Example auth posture:

```yaml
auth:
  enabled: true
  backend: config
  public_paths:
    - /health
    - /ready
    - /metrics
  keys:
    - id: ops
      hash: "<bcrypt-or-configured-hash>"
      label: "ops"
      kb_allowlist: ["default"]
      scopes: ["search", "rebuild", "admin"]
```

Use API keys with the narrowest practical scopes. `search` can query; `rebuild` can mutate managed-library state and rebuild; `admin` is required for destructive or operator-review actions such as hard delete and feedback review.

Example profiles are available under `examples/config/`:

- `local-hashing-npz.yaml`
- `local-sqlite-registry.yaml`
- `qdrant.yaml`
- `s3-blob.yaml`
- `answer-openai-compatible.yaml`

Validate a profile before starting the process:

```bash
python -m tagmemorag config validate --config examples/config/local-hashing-npz.yaml
```

`config validate` checks static/local prerequisites: config parsing, local writable paths, required env var names for configured remote providers, optional Python extras, and auth/metrics posture. It does not contact Qdrant, S3, embedding, reranker, answer, OCR, or visual providers, and it reports env var names only, never secret values.

Run live provider probes only when you intentionally want to contact configured remote services:

```bash
python -m tagmemorag provider probe --config examples/config/answer-openai-compatible.yaml --answer
python -m tagmemorag provider probe --config examples/config/qdrant.yaml --qdrant
python -m tagmemorag provider probe --config config.yaml --all
```

Provider probes are minimal and explicit. They can validate configured embedding, answer, reranker, Qdrant, or S3 connectivity, but output remains bounded: no secret values, Authorization headers, raw response bodies, generated answer text, vectors, or raw document text.

Use these readiness layers together:

| Layer | What it proves |
| --- | --- |
| `config validate` | Config coherence and local prerequisites. |
| `provider probe` | Explicit live connectivity for selected remote providers. |
| `readiness smoke` | Deterministic local build/retrieve/answer/queryplan/bundle composition. |
| `pilot run` | One retained pre-pilot report over config validation, provider probes, readiness smoke, and a sanitized eval fixture summary. |
| `/ready` | The running process has warmed up and loaded a KB for traffic. |

For the operator sequence and report retention guidance, see [Production Pilot Runbook](production-pilot-runbook.md).

## Persistence Matrix

Back up these stores according to the profile you run:

| Store | Default path/service | Backup note | Restore note |
| --- | --- | --- | --- |
| Graph/vector/anchor/meta artifacts | `data/{kb}/` | Can be rebuilt from sources, but useful for fast restore. | Restore with matching config/model versions or rebuild. |
| QueryPlan log | `data/{kb}/query_plans.db` | SQLite file; checkpoint WAL before file copy when possible. | Optional for serving; needed for replay/eval history. |
| Managed sidecar library | `product_manuals/{kb}/` | Source manuals plus `*.metadata.json`. | Rebuild after restore. |
| SQLite manual registry | `data/manual_registry.sqlite3` | Back up with SQLite-safe copy/checkpoint. | Restore alongside blob store; run `verify-blobs`. |
| Local manual blobs | `data/manual_blobs/` | Back up with registry at the same point in time. | Registry rows point to these blob keys. |
| S3-compatible blobs | configured bucket/prefix | Managed outside TagMemoRAG through bucket backup/lifecycle policy. | Restore bucket/prefix before registry-backed rebuild. |
| Qdrant vectors | Qdrant collection(s) | Use Qdrant-native snapshot/backup tooling. | If unavailable, switch to `vector_store.provider=npz` or rebuild after Qdrant returns. |
| Bundles | operator-chosen path | Store with normal backup controls. | Inspect before import; bundles restore sources, not serving graph state. |
| Config/secrets | deployment system | Version config templates; store secrets in secret manager/env. | Restore before starting service. |

Portable bundles are the preferred manual-library migration artifact:

```bash
python -m tagmemorag manual-library bundle export \
  --kb default \
  --config config.yaml \
  --output backups/default.bundle.zip

python -m tagmemorag manual-library bundle inspect \
  --bundle backups/default.bundle.zip \
  --config config.yaml \
  --target-kb restored
```

Bundles include safe manifests, checksums, metadata records, and source bytes. They do not include Qdrant dumps, generated vectors, credentials, signed URLs, stack traces, absolute paths, or raw search query text.

## First Run Checklist

1. Configure storage root and model/provider settings.
2. Run `python -m tagmemorag config validate --config config.yaml`.
3. Run `python -m tagmemorag readiness smoke` locally for MVP composition.
4. Run `python -m tagmemorag pilot run --config config.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --output .tmp/production-pilot/report.json` and retain the report.
5. Start the service.
6. Confirm `/health` and `/ready`.
7. Build or restore a KB.
8. Run a smoke search.
9. Check graph info and diagnostics.

Useful commands:

```bash
python -m tagmemorag build --docs docs/ --kb default --config config.yaml
python -m tagmemorag search "蒸汽很小" --kb default --top-k 5 --config config.yaml
curl -s http://127.0.0.1:8000/graph_info
curl -s "http://127.0.0.1:8000/manual-library/diagnostics?kb_name=default"
```

If auth is enabled, include `Authorization: Bearer ...` for protected endpoints.

## Managed Library Operations

File-sidecar mode is the default. Mutations mark a KB dirty but do not affect the served graph until rebuild succeeds.

```bash
python -m tagmemorag manual-library dirty --kb default --format json
python -m tagmemorag manual-library rebuild --kb default --mode auto --config config.yaml
```

Enable queueing only when you need coalescing, retry, or cancellation around repeated rebuild pressure:

```yaml
manual_library:
  rebuild_queue_enabled: true
  rebuild_queue_max_workers: 1
  rebuild_queue_max_attempts: 2
  rebuild_queue_retry_backoff_seconds: 5.0
```

The queue is process-local. After a restart, inspect dirty state and enqueue a fresh rebuild if needed. It is not a durable external queue.

Admin diagnostics live at:

```text
http://127.0.0.1:8000/admin/manual-library
```

The diagnostics endpoint groups dirty state, registry/blob status, queue jobs, Qdrant summaries, and recovery recommendations:

```bash
curl -s "http://127.0.0.1:8000/manual-library/diagnostics?kb_name=default"
```

## SQLite Registry And Blob Stores

Enable local registry mode:

```yaml
manual_library:
  registry_backend: sqlite
  registry_path: data/manual_registry.sqlite3
  blob_backend: local
  blob_root_dir: data/manual_blobs
```

Migrate existing sidecars without deleting them:

```bash
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml --dry-run
python -m tagmemorag manual-library registry migrate --kb default --config config.yaml
python -m tagmemorag manual-library registry verify-blobs --kb default --config config.yaml
```

Enable S3-compatible blob storage:

```yaml
manual_library:
  registry_backend: sqlite
  registry_path: data/manual_registry.sqlite3
  blob_backend: s3
  s3_bucket: tagmemorag-manuals
  s3_prefix: manuals/prod
  s3_endpoint_url: http://minio:9000
  s3_region: us-east-1
  s3_access_key_env: TAGMEMORAG_S3_ACCESS_KEY
  s3_secret_key_env: TAGMEMORAG_S3_SECRET_KEY
  s3_addressing_style: path
```

Credentials are read from the named environment variables. Set both credential env-name fields to empty strings only when you deliberately want boto3's default credential chain. Registry rows store safe object keys only, not signed URLs or credentials.

S3 mode requires the optional dependency:

```bash
uv sync --extra s3
```

For a container image, bake the optional extra into the image you deploy or use local blob mode.

## Qdrant Operations

Qdrant is optional. Local NPZ remains the default vector store and the simplest rollback target.

```yaml
vector_store:
  provider: qdrant
  qdrant_url: http://qdrant:6333
  collection_prefix: tagmemorag
```

Inspect alignment between the loaded graph and Qdrant:

```bash
python -m tagmemorag qdrant inspect --kb default --config config.yaml
```

If Qdrant is unavailable during rebuild, the old graph remains serving and dirty state remains pending. Recovery options:

1. Restore Qdrant connectivity and retry incremental/auto rebuild.
2. Force a full rebuild if point reuse or stale-delete state is uncertain.
3. Temporarily switch to `vector_store.provider=npz` and rebuild from managed sources if Qdrant must stay offline.

Do not treat Qdrant ANN as authoritative ranking. It is candidate generation only; final ranking remains local and deterministic over loaded graph/vector state.

## Bundle Restore And Migration

Restore into a target KB:

```bash
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

python -m tagmemorag manual-library rebuild --kb restored --mode full --config config.yaml
```

Use `--conflict-mode skip` for additive import and `overwrite` only when you intend to replace target records. Import marks manuals dirty and pending rebuild; it does not automatically make imported content searchable.

For local-to-S3 migration, configure the target with SQLite registry plus S3 blob store, inspect the bundle against that config, import, run `verify-blobs`, then rebuild.

## Observability

Metrics are enabled by default at `/metrics` and tracing is disabled by default:

```yaml
observability:
  metrics:
    enabled: true
    path: /metrics
    include_runtime: true
  tracing:
    enabled: false
```

Logs default to JSON in deployment:

```yaml
logging:
  level: INFO
  format: json
```

Safe telemetry may include low-cardinality fields such as `kb_name`, `route`, `status_code`, `error_code`, `operation`, `outcome`, `strategy`, and bounded skip reasons. It must not include raw query text, document chunks, vectors, API keys, credential values, signed URLs, full source paths, or unbounded candidate ids.

Minimum operational checks:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/metrics >/tmp/tagmemorag.metrics
python -m tagmemorag manual-library dirty --kb default --format json
```

## Rollback Playbooks

### Bad Config

1. Restore the previous config/env.
2. Restart the service.
3. Check `/ready`.
4. Run a smoke search.

### Failed Rebuild

1. Inspect `manual-library dirty`.
2. Check task/job error summary.
3. Fix the reported storage, embedding, parser, or Qdrant issue.
4. Retry `mode=auto` or `incremental`.
5. Use `mode=full` if compatibility or stale vector state is uncertain.

Old graph state keeps serving until a rebuild successfully saves and swaps.

### Qdrant Outage

1. Restore Qdrant service.
2. Run `qdrant inspect`.
3. Retry rebuild.
4. If outage is prolonged, switch to `vector_store.provider=npz`, restart, and rebuild.

### S3/Object Store Outage

1. Restore bucket/prefix/network/credentials.
2. Run `manual-library registry verify-blobs`.
3. Retry rebuild or queued job.
4. If you migrated from sidecars and kept local files, switch `registry_backend=file` for an emergency rebuild path.

### Registry/Blob Drift

1. Run `registry inspect` and `verify-blobs`.
2. Restore missing blobs or registry backup.
3. If source bundle exists, import into a clean target KB and rebuild.
4. Avoid editing SQLite rows by hand unless you have an offline backup and a precise recovery plan.

### Bad Bundle Import

1. If validation failed, no registry rows should have been written; fix the bundle/config and retry.
2. If import succeeded but rebuild failed, fix the rebuild issue and retry; imported records remain dirty.
3. For unwanted imported records, use existing manual delete/disable APIs or restore from backup, then rebuild.

### Queue Stuck Or Superseded

1. Inspect rebuild jobs.
2. Cancel queued or retrying jobs that are obsolete.
3. Submit one `mode=full` job if state is uncertain.
4. Disable `manual_library.rebuild_queue_enabled` to return to immediate rebuild behavior.

## Multi-Replica Boundary

Read-only replicas can serve the same built artifacts only if your deployment system controls synchronization and reload timing. TagMemoRAG does not currently coordinate:

- multiple writers mutating one SQLite registry
- multiple process-local rebuild queues
- leader election
- cross-replica cache invalidation
- Qdrant collection swaps across app replicas
- object-store event/webhook fanout

Recommended conservative topology:

1. One writer/admin instance handles uploads, imports, registry changes, and rebuilds.
2. Generated artifacts and source stores are backed up externally.
3. Additional serving instances are introduced only with an explicit artifact synchronization and reload plan.

When in doubt, run a single app instance and scale the external embedding/Qdrant/object-store services first.
