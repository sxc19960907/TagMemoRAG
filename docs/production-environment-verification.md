# Production Environment Verification

This checklist is for the first production-like verification pass after a release branch has merged. It is intentionally split into local deterministic checks and explicit live-provider checks so operators know exactly when external systems are contacted.

Do not paste secret values into YAML, docs, tickets, shell history captures, or retained reports. TagMemoRAG config names environment variables such as `SILICONFLOW_API_KEY`; the secret values stay in the deployment environment or secret manager.

## Evidence Directory

Use one retained directory per verification run:

```bash
export TMR_VERIFY_DIR=.tmp/production-env-verification/$(date +%Y%m%d-%H%M%S)
mkdir -p "$TMR_VERIFY_DIR"
```

Retain these artifacts when produced:

- `config-validate.json`
- `provider-probe-*.json`
- `readiness-smoke.json`
- `pilot-report.json`
- `health.txt`, `ready.txt`, and `metrics.prom`
- manual-library dirty / registry / blob inspection JSON

Review artifacts before sharing them outside the operations team. They are designed to avoid secrets and raw document text, but deployment-specific paths and service names may still be sensitive.

## Required Inputs

Choose the config file under verification:

```bash
export TMR_CONFIG=config.yaml
export TMR_KB=default
```

Set only the env vars required by the configured providers:

| Surface | Config fields | Typical env vars |
| --- | --- | --- |
| HTTP embedding | `model.provider=http`, `model.api_key_env` | `SILICONFLOW_API_KEY` |
| Reranker | `reranker.enabled=true`, `reranker.api_key_env` | `SILICONFLOW_API_KEY` |
| Answer generation | `answer.enabled=true`, `answer.api_key_env` | `OPENAI_API_KEY` or provider-specific key |
| S3-compatible blobs | `manual_library.blob_backend=s3` | `TAGMEMORAG_S3_ACCESS_KEY`, `TAGMEMORAG_S3_SECRET_KEY`, optional session token |
| Qdrant | `vector_store.provider=qdrant` | Usually none, unless your deployment adds network auth outside TagMemoRAG |

If a provider is intentionally disabled, do not set credentials just to run this checklist.

## Static Config Validation

This command is local and should not contact remote providers:

```bash
python -m tagmemorag config validate --config "$TMR_CONFIG" > "$TMR_VERIFY_DIR/config-validate.json"
```

Pass condition:

- JSON `status` is not `failed`.
- Warnings are understood and either accepted for the pilot or fixed before live checks.

Stop if required env var names, local writable paths, optional dependencies, or auth posture are wrong.

## Local Aggregate Report

For a repeatable local artifact over the deterministic parts of this checklist, run:

```bash
uv run python scripts/production_verify.py \
  --config "$TMR_CONFIG" \
  --workdir "$TMR_VERIFY_DIR/local-report" \
  --output "$TMR_VERIFY_DIR/production-verification.json"
```

This script runs static config validation, readiness smoke, and a retained pilot report. It does not run live provider probes unless you explicitly pass `--probe`, for example:

```bash
uv run python scripts/production_verify.py \
  --config "$TMR_CONFIG" \
  --probe embedding \
  --probe qdrant \
  --workdir "$TMR_VERIFY_DIR/live-report" \
  --output "$TMR_VERIFY_DIR/production-verification-live.json"
```

Use the script output as the summary artifact, and keep the step-specific files below when you need more detailed operator evidence.

## Live Provider Probes

These commands may call external systems. Run only the probes for providers enabled in the target profile:

```bash
python -m tagmemorag provider probe --config "$TMR_CONFIG" --embedding > "$TMR_VERIFY_DIR/provider-probe-embedding.json"
python -m tagmemorag provider probe --config "$TMR_CONFIG" --reranker > "$TMR_VERIFY_DIR/provider-probe-reranker.json"
python -m tagmemorag provider probe --config "$TMR_CONFIG" --answer > "$TMR_VERIFY_DIR/provider-probe-answer.json"
python -m tagmemorag provider probe --config "$TMR_CONFIG" --qdrant > "$TMR_VERIFY_DIR/provider-probe-qdrant.json"
python -m tagmemorag provider probe --config "$TMR_CONFIG" --s3 > "$TMR_VERIFY_DIR/provider-probe-s3.json"
```

For a full intentionally-live sweep:

```bash
python -m tagmemorag provider probe --config "$TMR_CONFIG" --all > "$TMR_VERIFY_DIR/provider-probe-all.json"
```

Pass condition:

- Enabled required providers report `passed`.
- Disabled or intentionally unavailable providers report `skipped` or a known accepted warning.
- No output includes secret values, Authorization headers, raw provider responses, generated answer text, vectors, or document text.

Stop if embedding, storage, or required answer/reranker providers fail for the target pilot profile.

## Local Composition Smoke

This command is deterministic and isolated; it does not prove live provider health:

```bash
python -m tagmemorag readiness smoke --keep-workdir > "$TMR_VERIFY_DIR/readiness-smoke.json"
```

Pass condition:

- JSON `status` is `passed`.
- Retained workdir path is captured in the JSON.

## Retained Pilot Report

Run the pilot report against the target config. Keep eval diagnosis policy explicit so known stress-test suites and reviewed production-embedder differences remain visible but do not block the stage:

```bash
python -m tagmemorag pilot run \
  --config "$TMR_CONFIG" \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl \
  --accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl \
  --workdir "$TMR_VERIFY_DIR/pilot-workdir" \
  --output "$TMR_VERIFY_DIR/pilot-report.json"
```

Pass condition:

- Exit code is `0`.
- Report `status` is `passed` or an explicitly accepted `warning`.
- Any `eval_reauthoring_diagnosis` warning is tied to non-informational, non-accepted suites and has an owner decision.

Do not accept `failed` reports for opening pilot traffic.

## Running Service Checks

After starting the target deployment, capture process checks:

```bash
curl -fsS http://127.0.0.1:8000/health > "$TMR_VERIFY_DIR/health.txt"
curl -fsS http://127.0.0.1:8000/ready > "$TMR_VERIFY_DIR/ready.txt"
curl -fsS http://127.0.0.1:8000/metrics > "$TMR_VERIFY_DIR/metrics.prom"
```

If auth, host, port, or TLS are configured differently, use the deployment URL and required Authorization header from the secret manager. Do not paste bearer tokens into retained command logs.

Pass condition:

- `/health` responds successfully.
- `/ready` responds successfully after warm-up and KB load.
- `/metrics` is reachable when metrics are enabled.

## Library And Backend Checks

Capture managed-library state:

```bash
python -m tagmemorag manual-library dirty \
  --kb "$TMR_KB" \
  --config "$TMR_CONFIG" \
  --format json > "$TMR_VERIFY_DIR/manual-library-dirty.json"
```

For SQLite registry profiles:

```bash
python -m tagmemorag manual-library registry inspect \
  --kb "$TMR_KB" \
  --config "$TMR_CONFIG" > "$TMR_VERIFY_DIR/manual-registry-inspect.json"

python -m tagmemorag manual-library registry verify-blobs \
  --kb "$TMR_KB" \
  --config "$TMR_CONFIG" > "$TMR_VERIFY_DIR/manual-registry-verify-blobs.json"
```

For Qdrant profiles:

```bash
python -m tagmemorag qdrant inspect \
  --kb "$TMR_KB" \
  --config "$TMR_CONFIG" > "$TMR_VERIFY_DIR/qdrant-inspect.json"
```

Pass condition:

- Dirty state is understood before opening traffic.
- Registry/blob checks pass for registry-backed profiles.
- Qdrant inspect shows expected graph/vector alignment for Qdrant-backed profiles.

## Stop Conditions

Do not continue to pilot traffic when any of these happen:

- Static config validation fails.
- Required live provider probe fails.
- Readiness smoke fails.
- Pilot report status is `failed`.
- `/ready` cannot pass after expected warm-up.
- Registry/blob verification reports missing required blobs.
- Qdrant-backed profile cannot inspect or rebuild expected vector state.

Use the rollback playbooks in `production-deployment-operations.md` for recovery.
