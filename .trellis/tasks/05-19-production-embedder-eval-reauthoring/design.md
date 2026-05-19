# Production embedder eval reauthoring design

## Boundary

The first deliverable is an offline diagnostic. It uses existing baseline files and does not call embedding providers or mutate eval suites.

In scope:

- `scripts/diagnose_eval_reauthoring.py`
- Unit tests for the diagnostic helpers and command behavior
- Documentation updates in `docs/eval-baseline-workflow.md` and README

Out of scope:

- Editing `tests/fixtures/eval/*.jsonl`
- Refreshing baseline files
- Calling SiliconFlow or any live provider
- Making SiliconFlow a CI gate

## Inputs

- Hashing baseline: default `tests/fixtures/eval/baselines/hashing.json`
- Production baseline: default `tests/fixtures/eval/baselines/siliconflow.json`
- Metrics: `precision_at_k`, `recall_at_k`, `mrr`, `hit_at_k`

## Output Contract

Schema version: `eval_reauthoring_diagnosis.v1`

Top-level fields:

- `schema_version`
- `hashing_baseline`
- `production_baseline`
- `hashing_embedder`
- `production_embedder`
- `summary`
- `suites`

Each suite row:

- `suite`
- `status`: `ok`, `monitor`, `reauthor`, or `investigate`
- `severity`: integer 0-3
- `hashing`: metric map
- `production`: metric map
- `delta`: production minus hashing
- `recommendation`: short reviewer action
- `reasons`: list of bounded strings

## Classification

The diagnostic is intentionally simple and deterministic:

- Missing in either baseline -> `investigate`, severity 3.
- Production `hit_at_k < 0.5` or `recall_at_k < 0.5` -> `investigate`, severity 3.
- Production recall delta <= -0.25 or MRR delta <= -0.25 -> `reauthor`, severity 2.
- Production recall delta <= -0.10 or MRR delta <= -0.10 -> `monitor`, severity 1.
- Otherwise -> `ok`, severity 0.

`precision_at_k` is reported but does not drive severity unless it is missing, because the existing eval docs treat precision as informational unless explicitly gated.

## CLI

```bash
python scripts/diagnose_eval_reauthoring.py \
  --hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --format markdown \
  --output .tmp/eval/reauthoring.md
```

Exit codes:

- `0`: diagnosis produced successfully.
- `2`: invalid baseline input or output format.

## Compatibility

The script lives under `scripts/` like the existing baseline tools so it can import project code minimally and remain optional. It reads baseline aggregate metrics only; no raw eval cases, queries, snippets, or vectors are emitted.
