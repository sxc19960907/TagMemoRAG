# Production Pilot Runbook

This runbook is a bounded pre-pilot gate for the MVP surfaces that already exist in TagMemoRAG. It does not certify the deployment as production-grade; it gives operators one repeatable record before opening a small pilot.

## Quick Local Pilot

Run the deterministic local profile first:

```bash
python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/production-pilot
```

To retain a reviewable report:

```bash
python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/production-pilot \
  --output .tmp/production-pilot/report.md \
  --format markdown
```

The command runs:

| Stage | Purpose | Failure behavior |
| --- | --- | --- |
| `config_validate` | Load config, check local writable paths, env-var names, optional dependencies, and auth/metrics posture. | `failed` fails the pilot; `warning` keeps the pilot in warning. |
| `provider_probe` | Probe configured remote providers through the existing explicit live-probe contract. | `failed` fails the pilot; all-skipped is acceptable for local/offline profiles. |
| `readiness_smoke` | Build/retrieve/answer/queryplan/bundle composition with deterministic local data. | Must pass. |
| `eval` | Retrieval fixture run with sanitized summary metrics. | Must pass the pilot thresholds. |

## Thresholds

The pilot default thresholds are intentionally local-profile friendly:

```text
recall_at_k >= 0.75
mrr >= 0.75
hit_at_k >= 0.8
```

Use stricter overrides when a rollout requires them:

```bash
python -m tagmemorag pilot run \
  --config config.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --min-recall-at-k 0.8 \
  --min-mrr 0.8 \
  --min-hit-at-k 0.9
```

For regression gating, prefer the eval baseline workflow:

```bash
python -m tagmemorag eval run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --baseline tests/fixtures/eval/baselines/hashing.json
```

## Production Profile Sequence

1. Validate the target profile:

   ```bash
   python -m tagmemorag config validate --config config.yaml
   ```

2. Probe each remote dependency intentionally:

   ```bash
   python -m tagmemorag provider probe --config config.yaml --embedding
   python -m tagmemorag provider probe --config config.yaml --qdrant
   python -m tagmemorag provider probe --config config.yaml --s3
   python -m tagmemorag provider probe --config config.yaml --answer
   python -m tagmemorag provider probe --config config.yaml --reranker
   ```

3. Run the pilot command and write a report:

   ```bash
   python -m tagmemorag pilot run \
     --config config.yaml \
     --suite tests/fixtures/eval/coffee.jsonl \
     --docs tests/fixtures \
     --workdir .tmp/production-pilot \
     --output .tmp/production-pilot/report.json
   ```

4. Start the service, verify `/health` and `/ready`, build or restore a KB, and run a smoke search against the pilot KB.

5. Attach the pilot report and retained workdir path to the rollout record.

## Report Privacy

The pilot report is designed for operator records. It includes stage names, statuses, provider/check counts, profile names, eval metric summaries, failed case ids, and next steps. It does not include raw eval queries, retrieved snippets, vectors, API keys, Authorization headers, raw provider responses, or full source-file lists.

If a stage fails, rerun the individual command for that stage with the same config to diagnose in detail.
