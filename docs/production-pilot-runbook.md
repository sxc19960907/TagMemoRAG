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

Attach the aggregate production-embedder diagnosis when reviewing pilot readiness:

```bash
python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl \
  --accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl \
  --workdir .tmp/production-pilot
```

When the diagnosis stage finds `monitor`, `reauthor`, or `investigate` suites, non-informational and non-accepted suites make the pilot status `warning`, not `failed`. Treat that as a review gate: decide whether the affected suites are acceptable for the pilot profile or need case-level inspection first. The known stress-test suites above stay visible in the diagnosis, but they do not make the stage warning when explicitly listed as informational. The accepted list records Phase B's review decision that `product_manuals`, `mixed_language`, and `tag_rerank_edge` are good enough for the production-embedder baseline even when lower than hashing.

Keep `coffee.jsonl` out of the accepted list unless the pilot owner explicitly signs off its current monitor-level divergence.

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

For a browser-first local trial, include the normal-user Q&A journey in the same retained pilot report:

```bash
python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/production-pilot \
  --output .tmp/production-pilot/report.json \
  --include-browser-qa
```

Use `--browser-qa-full` with `--include-browser-qa` before release-style local closure or when broad browser/admin flows changed. Keep the browser stage opt-in because it starts a local server and runs Playwright.

The command runs:

| Stage | Purpose | Failure behavior |
| --- | --- | --- |
| `config_validate` | Load config, check local writable paths, env-var names, optional dependencies, and auth/metrics posture. | `failed` fails the pilot; `warning` keeps the pilot in warning. |
| `provider_probe` | Probe configured remote providers through the existing explicit live-probe contract. | `failed` fails the pilot; all-skipped is acceptable for local/offline profiles. |
| `readiness_smoke` | Build/retrieve/answer/queryplan/bundle composition with deterministic local data. | Must pass. |
| `browser_qa_readiness` | Optional browser-first Q&A flow, including demo manual, Q&A, citations, feedback, Retrieval Quality, and eval draft launch. | Included only with `--include-browser-qa`; must pass when included. |
| `answer_quality` | Run deterministic answer-quality diagnostics for groundedness, citation support, refusal behavior, and conflict handling. | Must pass unless explicitly skipped with `--skip-answer-quality`. |
| `eval` | Retrieval fixture run with sanitized summary metrics. | Must pass the pilot thresholds. |
| `eval_reauthoring_diagnosis` | Optional hashing-vs-production baseline diagnosis. | Non-informational, non-accepted warnings require reviewer signoff; informational and accepted suites are retained in detail but do not gate the stage. Invalid baseline input fails. |

The answer-quality stage defaults to
`tests/fixtures/answer_quality/basic.jsonl` and is offline: it does not call a
live answer provider. Override it with `--answer-quality-suite <jsonl>` for a
profile-specific fixture, or use `--skip-answer-quality` only when the pilot
owner deliberately wants a retrieval-only gate.

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
