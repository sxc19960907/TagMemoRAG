#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-examples/config/qa-demo.yaml}"
DOCS_DIR="$ROOT_DIR/.tmp/tagmemorag-qa-demo/docs"

mkdir -p "$DOCS_DIR"
cp "$ROOT_DIR/tests/fixtures/coffee_machine.md" "$DOCS_DIR/coffee_machine.md"

cd "$ROOT_DIR"
uv run python -m tagmemorag build \
  --docs "$DOCS_DIR" \
  --kb default \
  --config "$CONFIG_PATH"
