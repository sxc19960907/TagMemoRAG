# Implementation Plan

1. Run `production-provider verify --level smoke` with env-only credentials and retained `.tmp` reports.
2. Inspect the verify summary and nested smoke report for parity/citation metrics.
3. Decide whether to run `--level pilot`; run it if practical, otherwise document the defer reason.
4. Add a sanitized verification doc under `docs/`.
5. Run targeted checks, archive, and commit.
