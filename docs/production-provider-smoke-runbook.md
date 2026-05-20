# Production Provider Smoke Runbook

This runbook is the operator path for local production-provider verification with Qdrant, MinIO, SiliconFlow, and DeepSeek.

## Prerequisites

- Docker is running.
- Local provider services can bind:
  - Qdrant: `127.0.0.1:6333`
  - MinIO: `127.0.0.1:9000`
- Required environment variables are set:
  - `SILICONFLOW_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `TAGMEMORAG_S3_ACCESS_KEY`
  - `TAGMEMORAG_S3_SECRET_KEY`

For the checked-in local Docker profile, MinIO defaults are:

```bash
export TAGMEMORAG_S3_ACCESS_KEY=tagmemorag
export TAGMEMORAG_S3_SECRET_KEY=tagmemorag-secret
```

Secret values must stay in the shell or secret manager. Do not write provider keys into YAML, docs, command logs, or reports.

## One-Command Smoke

```bash
uv run python scripts/run_production_provider_smoke.py
```

By default the runner:

1. Checks required environment variable names without printing values.
2. Starts local Docker provider services with `docker compose --profile providers up -d qdrant minio`.
3. Ensures the configured MinIO bucket exists.
4. Runs:

```bash
python -m tagmemorag production-provider smoke \
  --config examples/config/production-provider-verification.yaml \
  --kb default \
  --manual product_manuals/washer/ASKO W6564.pdf \
  --workdir .tmp/production-provider-verification/operator-smoke \
  --output .tmp/production-provider-verification/operator-smoke-report.json \
  --format json \
  --question 'ASKO W6564 洗衣机不排水时应该检查什么？' \
  --reset-qdrant-collection
```

The generated smoke report stays under `.tmp/` and is not committed.

## Common Options

```bash
# Check env/service setup without running the RAG smoke.
uv run python scripts/run_production_provider_smoke.py --check-only

# Use another manual.
uv run python scripts/run_production_provider_smoke.py \
  --manual 'product_manuals/oven/HISENSE BSA5221.pdf'

# Keep existing provider services untouched.
uv run python scripts/run_production_provider_smoke.py --skip-docker

# Do not reset Qdrant collection before rebuild.
uv run python scripts/run_production_provider_smoke.py --no-reset-qdrant

# Write markdown output.
uv run python scripts/run_production_provider_smoke.py \
  --format markdown \
  --output .tmp/production-provider-verification/operator-smoke-report.md
```

## Expected Passing Evidence

A passing run should show:

- `required_env`: passed
- `docker_providers`: passed or skipped by operator choice
- `s3_bucket`: passed
- `production_provider_smoke`: passed

Inside the smoke report, the important sanitized stage metrics are:

- `provider_probe`: 5 passed
- `qdrant_reset`: passed with `action=deleted` or `action=absent`
- `manual_import`: imported count greater than 0
- `blob_verify`: missing count 0
- `manual_library_rebuild`: embedded chunk count greater than 0
- `qdrant_inspect`: missing vector count 0
- `answer_smoke`: answer kind `answer` and citation count greater than 0

## Troubleshooting

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| `required_env` failed | One or more env vars are missing | Export the missing env names shown in the runner output. |
| Docker port bind failure | Qdrant or MinIO is already running | Use `--skip-docker` if the existing services are intended. |
| `s3_bucket` failed | MinIO not reachable or credentials mismatch | Check `docker ps`, MinIO health, and `TAGMEMORAG_S3_*` values. |
| `provider_probe` failed | External provider key/model/network issue | Run `python -m tagmemorag provider probe --config examples/config/production-provider-verification.yaml --all`. |
| `qdrant_inspect.missing_vector_count > 0` | Rebuild/vector sync mismatch | Rerun with `--reset-qdrant-collection`; if it persists, inspect rebuild errors. |
| `answer_smoke` failed | Retrieval unanswerable or answer provider failure | Check provider probe, answer warnings, and whether the manual/query match. |

## Report Retention

Keep only sanitized summaries in repo docs. Raw `.tmp/` smoke reports are local runtime artifacts and may contain environment-specific paths or operational traces.
