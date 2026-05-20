# Production Deployment And Operations Guide — Design

## Scope

This is a documentation-only operations task. It does not add deployment automation, change Docker defaults, alter config semantics, or add runtime health checks.

## Source Of Truth

- `Dockerfile` and `docker-compose.yml` define the current container entrypoint, healthcheck, data mount, read-only root filesystem, and SQLite helper profile.
- `.env.example` documents the supported environment override style.
- `config.yaml` and `src/tagmemorag/config.py` define available config blocks and defaults.
- Archived M26-M30 tasks define registry/blob/queue/diagnostics/bundle behavior.
- Backend specs define persistence, S3, observability, logging, and safety boundaries.

## Guide Structure

1. Operational status and limits
2. Deployment profiles
3. Docker Compose baseline
4. Configuration and secrets
5. Persistence and backup matrix
6. First-run and readiness checks
7. Managed-library operations
8. Qdrant and vector-store operations
9. Registry/blob-store operations
10. Bundle import/export recovery
11. Observability and diagnostics
12. Rollback playbooks
13. Multi-replica notes and unsupported HA boundary

## Safety Rules

- Use placeholder env values only.
- Never show real API keys, signed URLs, raw document text, vectors, Qdrant payload dumps, or absolute machine paths.
- Present S3 and Qdrant as opt-in services; local NPZ/file mode remains valid.
- State that the rebuild queue is process-local and not durable by default.
- Treat bundles as portable recovery artifacts, not authoritative graph/vector snapshots.

## Validation

- Grep for unsupported claims: built-in HA, leader election, encrypted/signed bundles, automatic object-store backup.
- Syntax-check shell snippets as static text when feasible.
- Run markdown/doc-focused checks available in this repo; if none exist, run `git diff --check` and focused config/docs tests.
