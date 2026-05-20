# Production environment verification prep design

## Output Shape

Add a focused runbook at `docs/production-environment-verification.md` and link it from the production operations guide.

## Command Flow

1. Confirm repo and dependency state.
2. Export or inject secrets through the deployment environment.
3. Run static config validation.
4. Run selected live provider probes.
5. Run deterministic local readiness smoke.
6. Run retained pilot report.
7. Check a running service's health, ready, and metrics endpoints.
8. Inspect managed-library state and optional registry/blob/vector backends.
9. Record pass/fail evidence and stop conditions.

## Safety Rules

- Commands may print env var names but never secret values.
- Use placeholders such as `<config.yaml>` and `<base-url>`.
- Keep live commands explicit and labeled as external-service calls.
- Keep local deterministic commands separate from live validation.

## Compatibility

This is documentation-only. It should not change runtime behavior.
