# TagMemoRAG MVP Delivery Guide

Date: 2026-05-20

This is the primary handoff guide for the current TagMemoRAG MVP. It summarizes the shortest reliable path to run the system, verify the live provider stack, and understand what is shipped versus deferred.

## Status

TagMemoRAG is **pilot-ready / technical pre-production**. It has a working product-manual RAG path with managed PDF ingestion, Qdrant vectors, S3-compatible source storage, SiliconFlow embedding and reranking, DeepSeek answer generation, citations, eval tooling, and operator verification commands.

It is not yet a fully managed production platform. Multi-tenant document ACLs, high availability, automatic backups, full observability operations, real production OCR/visual/connectors providers, and UI-level rollout tooling remain deferred.

## What Is Shipped

| Area | Status | Notes |
| --- | --- | --- |
| Product-manual parsing and chunking | Shipped | Markdown, TXT, text PDF, page metadata, table-aware chunking, OCR fallback boundary |
| Managed manual library | Shipped | SQLite registry, local/S3 blobs, dirty state, rebuild, bundle import/export |
| Retrieval | Shipped | Vector, lexical, metadata, graph, evidence-aware `/retrieve` |
| Qdrant | Shipped | Optional vector backend, ANN preselection, point-level sync, inspect tooling |
| QueryPlan and replay | Shipped | SQLite plan log, replay/eval driver |
| Reranker | Shipped | First-class reranker component, SiliconFlow provider, fallback path |
| Answer endpoint | Shipped | Optional `/answer`, OpenAI-compatible provider, citation validation |
| Verification | Shipped | `readiness smoke`, `pilot run`, `production-provider verify` |
| OCR | Default-off foundation | Deterministic fixture provider shipped; production OCR provider deferred |
| Visual retrieval | Default-off foundation | Deterministic visual candidate/rerank boundary shipped; production model deferred |
| Connectors | Default-off foundation | Fixture connector shipped; real SaaS connectors deferred |

## Prerequisites

- Python environment managed by `uv`.
- Docker running locally.
- Provider services can bind:
  - Qdrant: `127.0.0.1:6333`
  - MinIO: `127.0.0.1:9000`
- Required live-provider environment variables:
  - `SILICONFLOW_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `TAGMEMORAG_S3_ACCESS_KEY`
  - `TAGMEMORAG_S3_SECRET_KEY`

For the checked-in local Docker profile, MinIO uses:

```bash
export TAGMEMORAG_S3_ACCESS_KEY=tagmemorag
export TAGMEMORAG_S3_SECRET_KEY=...
```

Keep provider credentials in the shell, local secret manager, or deployment secret store. Do not write credential values into YAML, docs, logs, or retained reports.

## Quick Verification Path

Use the unified production-provider verifier as the main live-provider gate:

```bash
export SILICONFLOW_API_KEY=...
export DEEPSEEK_API_KEY=...
export TAGMEMORAG_S3_ACCESS_KEY=tagmemorag
export TAGMEMORAG_S3_SECRET_KEY=...

uv run python -m tagmemorag production-provider verify \
  --level smoke \
  --verify-output .tmp/production-provider-verification/verify-summary.json
```

If Qdrant and MinIO are already running and Docker compose startup is not desired:

```bash
uv run python -m tagmemorag production-provider verify \
  --level smoke \
  --skip-docker \
  --verify-output .tmp/production-provider-verification/verify-summary.json
```

A passing smoke should show:

- `required_env`: passed
- `docker_providers`: passed or skipped by operator choice
- `s3_bucket`: passed
- `production_provider_smoke`: passed
- nested `provider_probe`: 5 passed
- nested `qdrant_inspect`: point count equals graph node count, missing vectors 0
- nested `answer_smoke`: answer kind `answer`, citation count greater than 0

See [Production Provider Smoke Runbook](production-provider-smoke-runbook.md) for command options and [Unified Verify CLI Live Verification](unified-verify-cli-live-verification.md) for the latest retained live evidence.

## Local Composition Check

Before touching live providers, run the deterministic local smoke:

```bash
uv run python -m tagmemorag readiness smoke
```

This validates local build, retrieve, noop answer generation, QueryPlan persistence, and bundle round-trip. It does not prove SiliconFlow, DeepSeek, Qdrant, or S3 reachability.

## Config Validation And Provider Probes

Validate config shape without contacting live providers:

```bash
uv run python -m tagmemorag config validate \
  --config examples/config/production-provider-verification.yaml
```

Probe configured live providers intentionally:

```bash
uv run python -m tagmemorag provider probe \
  --config examples/config/production-provider-verification.yaml \
  --all
```

Provider probe output is sanitized: it reports provider names and statuses, not credentials, auth headers, provider bodies, generated answers, vectors, or document content.

## Managed PDF Ingestion

The live verification profile uses the default ASKO W6564 manual:

```text
product_manuals/washer/ASKO W6564.pdf
```

For day-to-day manual operations, use the managed library commands:

```bash
uv run python -m tagmemorag manual-library dirty \
  --kb default \
  --config examples/config/production-provider-verification.yaml

uv run python -m tagmemorag manual-library rebuild \
  --kb default \
  --mode full \
  --config examples/config/production-provider-verification.yaml
```

For bulk upload flows, preview before committing:

```bash
uv run python -m tagmemorag manual-bulk preview \
  --kb default \
  --config examples/config/production-provider-verification.yaml \
  --metadata manuals.csv \
  --metadata-format csv \
  --file manual.pdf
```

Detailed registry, blob, queue, and bundle operations live in [Production Deployment And Operations](production-deployment-operations.md).

## Retrieve, Search, And Answer

Use CLI search for a quick retrieval check:

```bash
uv run python -m tagmemorag search \
  "ASKO W6564 洗衣机不排水时应该检查什么？" \
  --kb default \
  --top-k 5 \
  --config examples/config/production-provider-verification.yaml
```

Use `/retrieve` as the primary API contract when an external client wants evidence and context packaging. Use `/answer` when the server should call the configured answer provider and return a managed cited answer.

Start the service:

```bash
uv run python -m tagmemorag serve \
  --config examples/config/production-provider-verification.yaml
```

Check process health:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

If auth is enabled in a target deployment, include the configured bearer token for protected endpoints.

## Pilot Gate

Run the local pilot gate with retained output:

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/production-pilot \
  --output .tmp/production-pilot/report.json
```

For the unified live-provider path:

```bash
uv run python -m tagmemorag production-provider verify \
  --level pilot \
  --pilot-suite tests/fixtures/eval/coffee.jsonl \
  --pilot-docs tests/fixtures \
  --pilot-output .tmp/production-provider-verification/pilot-report.json
```

Run live pilot only when the operator has chosen the eval suite/baselines and accepted the provider cost/runtime. See [Production Pilot Runbook](production-pilot-runbook.md) for diagnosis policy, informational suites, and accepted-suite handling.

## Report Retention

Keep raw reports under `.tmp/`. Commit only sanitized summaries.

Safe retained summaries may include:

- stage names and statuses
- provider/check counts
- graph node count and Qdrant point count
- missing vector count
- answer kind, model id, text length, and citation count
- sanitized next steps

Do not retain in repo docs:

- credential values
- auth headers
- provider response bodies
- generated answer bodies
- retrieval excerpts
- vectors
- raw `.tmp` report payloads

## Common Troubleshooting

| Symptom | First Check | Action |
| --- | --- | --- |
| Missing env check fails | Required variable names in report | Export the missing env vars; do not put key values in YAML |
| Docker provider startup fails | `docker ps`, port bindings | If services are already running, rerun verify with `--skip-docker`; otherwise free ports 6333/9000 |
| S3 bucket fails | MinIO health and credentials | Check `TAGMEMORAG_S3_*` values and MinIO endpoint |
| Provider probe fails | Provider name and status | Verify key, base URL, model name, and network connectivity |
| Qdrant missing vectors | nested `qdrant_inspect` | Rerun with Qdrant reset; inspect rebuild errors if it persists |
| Answer smoke fails | provider probe and answer warnings | Confirm retrieval is answerable and answer token budget is sufficient |
| `/ready` fails after boot | KB load and model warm-up | Build or restore a KB, then recheck readiness |

## Deferred Production Gaps

These are known gaps, not hidden bugs:

- Document-level ACL and multi-tenant permissions.
- Multi-replica write coordination and leader election.
- Durable distributed rebuild queue.
- Automatic object-store and Qdrant backup/restore automation.
- Full alerting, SLO dashboards, and audit workflows.
- Streaming answers, multi-turn state, generation cache, and tool calling.
- Production OCR backend and layout-aware OCR.
- Production visual encoder/reranker and visual answer generation.
- Real SaaS connectors, OAuth, webhooks, connector ACL mapping, and credential rotation.
- Clean-environment handoff verification from a fresh checkout.

## Handoff Checklist

1. Confirm provider keys are available only as environment variables.
2. Run `readiness smoke` for local composition.
3. Run `production-provider verify --level smoke` for live provider verification.
4. Retain sanitized summary metrics, not raw reports.
5. Run pilot gate with the selected suite/baseline.
6. Start the service and verify `/health` and `/ready`.
7. Run one search/retrieve/answer smoke query against the target KB.
8. Record any deviations as follow-up tasks before opening a pilot to users.
