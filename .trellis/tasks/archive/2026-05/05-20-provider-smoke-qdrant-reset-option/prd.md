# Provider Smoke Qdrant Reset Option

## Goal

Let operators run production-provider smoke with a clean Qdrant verification collection so point-count metrics are not polluted by previous local runs.

## Requirements

- Add an explicit opt-in CLI flag for `production-provider smoke`.
- Reset only the configured smoke KB collection when `vector_store.provider=qdrant`.
- Run the reset before manual import/rebuild/Qdrant inspect.
- Include a sanitized reset stage in the smoke report.
- Keep the default behavior unchanged.
- Do not reset anything for non-Qdrant profiles; report a skipped stage.

## Acceptance Criteria

- [x] `production-provider smoke --reset-qdrant-collection` is accepted by the CLI.
- [x] Report includes `qdrant_reset` with deleted/absent/skipped status and collection name.
- [x] Unit tests cover CLI wiring and reset behavior without a real Qdrant service.
- [x] Existing smoke tests and broader unit/e2e tests pass.

## Notes

- This is a small operator-experience enhancement scoped to the production-provider smoke command.
