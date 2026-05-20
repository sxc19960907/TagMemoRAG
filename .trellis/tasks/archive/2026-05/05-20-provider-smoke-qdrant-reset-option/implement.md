# Implementation Plan

1. Add a Qdrant reset helper in the smoke orchestration module.
2. Wire `--reset-qdrant-collection` through CLI to the smoke runner.
3. Add unit tests for reset stage outcomes and CLI argument wiring.
4. Run focused tests, then unit/e2e without perf.
