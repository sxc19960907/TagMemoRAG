# Clean Environment Delivery Verification

## Goal

Verify the MVP delivery guide from an isolated runtime workspace so the handoff path is not dependent on prior `.tmp` state or existing generated reports.

## Requirements

- Use the merged `docs/mvp-delivery-guide.md` as the operator checklist.
- Run checks with isolated `.tmp/clean-env-delivery/*` runtime paths where practical.
- Do not commit generated runtime reports, provider outputs, or secrets.
- Record sanitized evidence in a docs report.
- Identify any handoff blockers or follow-ups discovered during the clean run.

## Acceptance Criteria

- [x] Local deterministic `readiness smoke` passes in an isolated workdir.
- [x] Unified live-provider smoke passes or has a documented environment-specific reason for any skipped step.
- [x] The delivery guide command help paths are verified.
- [x] A sanitized clean-environment verification report is committed.
- [x] No `.tmp` runtime report or secret value is committed.
