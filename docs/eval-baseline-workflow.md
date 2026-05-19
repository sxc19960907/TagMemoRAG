# Eval Baseline Workflow

The `tests/fixtures/eval/` suites are gated by per-suite baselines under `tests/fixtures/eval/baselines/`. This document describes when to refresh them, who reviews the diff, and how the two embedder profiles relate.

## Two profiles, two baselines

| File | Embedder | Used by |
|---|---|---|
| `baselines/hashing.json` | `HashingEmbedder` (dim=64, deterministic, no network) | **Quality CI** (gate) |
| `baselines/siliconflow.json` | `Qwen/Qwen3-Embedding-8B` via SiliconFlow HTTP API | local sanity only |

The hashing baseline is the only one CI consumes. SiliconFlow is a smoke check for divergence between the test embedder and what production-like deployments use.

## When to refresh `hashing.json`

Refresh **deliberately**, not reactively. Refresh after any of:

1. A suite under `tests/fixtures/eval/` is added, removed, or has cases edited.
2. A search-side change is intentional and improves the metrics (Phase 1+ rerank work).
3. A search-side change is intentional and trades off a metric (with explicit reviewer signoff).

Do **not** refresh the baseline simply because CI fails. A fail is a signal — investigate it first.

```bash
uv run python scripts/build_eval_baseline.py \
  --embedder hashing \
  --output tests/fixtures/eval/baselines/hashing.json
```

The script is deterministic except for `captured_at`. Two runs back-to-back should produce JSON that diffs only on that timestamp.

## When to refresh `siliconflow.json`

Refresh when the **production embedder** changes (model version, dim, normalization) or when investigating a CI vs production mismatch.

```bash
export SILICONFLOW_API_KEY=...        # required
scripts/eval-siliconflow.sh
git diff -- tests/fixtures/eval/baselines/siliconflow.json
```

The shell script wraps `build_eval_baseline.py --embedder siliconflow` with the env-var check.

## Diagnosing production-embedder reauthoring

Before editing any fixture JSONL, generate the offline reauthoring diagnosis:

```bash
uv run python scripts/diagnose_eval_reauthoring.py --format markdown
```

The diagnostic compares `baselines/hashing.json` with `baselines/siliconflow.json`, sorts suites by severity, and recommends `ok`, `monitor`, `reauthor`, or `investigate`. It is intentionally offline: it reads only committed aggregate baseline metrics and does not call SiliconFlow, refresh baselines, rewrite fixtures, or promote SiliconFlow to a CI gate.

Use the report as the queue for human fixture review:

- `investigate`: production metrics are too low or suite coverage is missing; inspect retrieval/model behavior before changing expected answers.
- `reauthor`: production aggregate deltas are large enough to justify case-level inspection and possible fixture edits.
- `monitor`: divergence exists but should not trigger fixture edits without case-level evidence.
- `ok`: no immediate fixture reauthoring is indicated.

## Reading a baseline diff

Every commit that touches a baseline must include a one-line rationale in the commit message. Example shapes:

- `chore(eval): refresh hashing baseline after adding mixed_language case` — additive change to a suite
- `feat(search): tag-rerank lifts mrr from 0.78 to 0.86 (mixed_language)` — quality improvement
- `fix(eval): hashing baseline regression triage — cause was X, fix in <commit>` — investigation

Reviewers should check:

1. The diff direction matches the rationale (no silent regressions hiding in the noise).
2. `config_hash` changes only when the configuration genuinely changed.
3. No suite was deleted from the baseline without the corresponding jsonl removal.

## Failure modes

| Symptom | Likely cause | Resolution |
|---|---|---|
| `baseline file not found` in CI | committed `hashing.json` was deleted | restore the file or regenerate with the script |
| `suite 'X' missing from baseline` | new jsonl added without baseline refresh | regenerate baseline, commit alongside the jsonl |
| `config_hash` drifts on every run | a suite file's content changed | rerun the script and review the metric diff |
| SiliconFlow run fails with HTTP 401/403 | invalid API key | rotate `SILICONFLOW_API_KEY`; do not commit the key |
| SiliconFlow run produces wildly different metrics from hashing | expected — the embedders see different signals | record the divergence in your task notes; do not gate on SiliconFlow |
