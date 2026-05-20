# Verify Docker Diagnostics Hardening

## Goal

Make `production-provider verify` handle Docker startup failures honestly and diagnosably.

## Requirements

- Keep Docker startup failure visible as a failed `docker_providers` check.
- Record bounded, sanitized stdout/stderr tails for failed subprocess checks.
- If Docker startup fails but subsequent S3 and nested smoke checks pass, aggregate the top-level verify status as `warning`, not `passed` and not `failed`.
- If Docker startup fails and required downstream checks do not pass, aggregate status remains `failed`.
- `--check-only` must still fail when Docker startup fails, because no downstream smoke proof exists.
- Update the runbook to explain `failed`, `warning`, and `skipped` Docker outcomes.

## Acceptance Criteria

- [x] Failed Docker command detail includes sanitized `stdout_tail` and/or `stderr_tail` when available.
- [x] Failed Docker plus passing S3 and nested smoke yields top-level status `warning`.
- [x] Failed Docker in check-only mode yields top-level status `failed`.
- [x] Failed nested smoke still yields top-level status `failed`, even if Docker diagnostics are present.
- [x] Tests cover the aggregation and sanitization behavior.
- [x] Runbook documents Docker startup failure semantics.
