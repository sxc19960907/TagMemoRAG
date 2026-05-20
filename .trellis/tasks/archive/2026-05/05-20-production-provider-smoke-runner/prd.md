# Production Provider Smoke Runner

## Goal

Provide a repeatable operator runner for the production-provider smoke path so local verification requires one command instead of several manual setup steps.

## Requirements

- Add a script under `scripts/` that can:
  - verify required provider environment variables are present without printing secret values;
  - start or verify local Qdrant/MinIO Docker services;
  - ensure the configured MinIO/S3 bucket exists;
  - run `tagmemorag production-provider smoke` with `--reset-qdrant-collection`;
  - write JSON or Markdown reports under `.tmp/` by default.
- Keep defaults aligned with `examples/config/production-provider-verification.yaml` and `product_manuals/washer/ASKO W6564.pdf`.
- Do not commit generated runtime reports or secrets.
- Add a runbook that documents prerequisites, command examples, outputs, and troubleshooting.

## Acceptance Criteria

- [x] Script exposes `--check-only`, config/manual/workdir/output/format/question options, and bucket/service controls.
- [x] Script fails fast with a sanitized missing-env report when required env vars are absent.
- [x] Unit tests cover argument construction and missing-env behavior without live Docker or provider calls.
- [x] Runbook documents the one-command local verification flow.
- [x] Focused tests and unit/e2e tests pass.

## Notes

- This is an operator-experience task; no production service behavior should change.
