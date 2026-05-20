# Production environment verification prep

## Goal

Prepare the first real-environment verification pass after the MVP/pilot merge by documenting a safe, repeatable command sequence that validates config, live providers, deterministic local readiness, and retained pilot reports without exposing secrets.

## Requirements

- Add an operator checklist for production-like environment verification.
- Keep the checklist safe by naming required env vars but never asking operators to write secret values into files or logs.
- Cover the current deployment surfaces:
  - config validation
  - live provider probes
  - readiness smoke
  - pilot report with eval diagnosis policy
  - service health/ready/metrics checks
  - manual-library dirty/registry/blob checks
- Include pass/fail evidence operators should retain.
- Do not run real provider probes in this task; credentials and target environment are operator-owned.

## Acceptance Criteria

- [ ] A docs page or runbook section lists the command sequence for real-environment verification.
- [ ] The checklist identifies required env vars by provider/profile.
- [ ] The checklist explains which commands are local/deterministic versus live/external.
- [ ] The checklist includes a safe report-retention convention under `.tmp/`.
- [ ] Existing deterministic verification still passes.

## Out of Scope

- Adding new provider implementations.
- Requiring real credentials in this repository.
- Changing deployment topology.
- Pushing or opening a PR for this new branch unless explicitly requested.
