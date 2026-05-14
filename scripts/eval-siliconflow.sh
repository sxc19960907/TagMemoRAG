#!/usr/bin/env bash
# Local sanity run: regenerate the SiliconFlow baseline file using the
# project's default model config (BAAI/bge-small-zh-v1.5 over the SiliconFlow
# HTTP API). Not part of CI — keep CI hashing-only.
set -euo pipefail

if [[ -z "${SILICONFLOW_API_KEY:-}" ]]; then
  echo "error: SILICONFLOW_API_KEY must be set in the environment" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_PATH="${1:-${REPO_ROOT}/tests/fixtures/eval/baselines/siliconflow.json}"

cd "${REPO_ROOT}"
uv run python scripts/build_eval_baseline.py \
  --embedder siliconflow \
  --output "${OUTPUT_PATH}"

echo
echo "Compare against the committed baseline:"
echo "  git diff -- ${OUTPUT_PATH}"
echo "If the diff is unexpected, see docs/eval-baseline-workflow.md before committing."
