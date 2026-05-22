#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.tmp/general-web-eval}"
KB_NAME="${2:-general_web}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

rm -rf "$ROOT_DIR"

"$PYTHON_BIN" -m tagmemorag knowledge sample-web \
  --url https://docs.python.org/3/tutorial/index.html \
  --url https://docs.github.com/en/get-started/start-your-journey/hello-world \
  --output-dir "$ROOT_DIR" \
  --kb "$KB_NAME" \
  --domain software_docs \
  --doc-type documentation \
  --tag software-docs \
  --timeout-seconds 20

cat <<EOF

General web eval corpus materialized at:
  $ROOT_DIR/$KB_NAME

Run:
  $PYTHON_BIN -m tagmemorag eval run \\
    --suite tests/fixtures/eval/general_web.jsonl \\
    --docs $ROOT_DIR/$KB_NAME \\
    --config examples/config/local-hashing-npz.yaml \\
    --kb $KB_NAME \\
    --top-k 5
EOF
