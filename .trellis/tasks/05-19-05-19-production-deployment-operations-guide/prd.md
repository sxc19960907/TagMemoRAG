# Production deployment and operations guide

## Goal

Create an operator-facing production deployment and operations guide that ties together the already-shipped Docker, Qdrant, SQLite registry, local/S3 blob store, rebuild queue, diagnostics, bundle import/export, auth, observability, and rollback surfaces.

## Requirements

- Add a durable guide under `docs/` that covers:
  - deployment profiles: local NPZ, Qdrant-backed, SQLite registry with local blobs, SQLite registry with S3-compatible blobs
  - Docker Compose startup and environment configuration
  - required persistent volumes / external durable services
  - health/readiness/metrics checks
  - auth and API-key posture
  - backup and restore for source manuals, SQLite registry, bundles, Qdrant collections, and config/secrets
  - safe rebuild, queue, dirty-state, and diagnostics operations
  - rollback playbooks for Qdrant outage, S3/object-store outage, registry/blob drift, failed rebuilds, bad import, and config rollback
  - multi-replica limits and the current single-writer/process-local queue boundary
- Update README to link to the guide from the operations/deployment area and milestone table.
- Keep documentation honest: no unsupported HA, no automatic multi-replica coordination claims, no credential examples with real secrets, no WAVE-as-critical-path language.
- Do not change runtime behavior.

## Acceptance Criteria

- [ ] `docs/production-deployment-operations.md` exists and gives concrete commands/checklists for deploy, verify, backup, restore, and rollback.
- [ ] README links to the new guide and the roadmap/milestone table no longer leaves the production deployment guide only as parking-lot prose.
- [ ] The guide references current config names from `config.yaml`, `.env.example`, and `docker-compose.yml`.
- [ ] The guide explicitly states current limits: single-machine/single-writer assumptions, process-local rebuild queue, no built-in leader election, no built-in object-store backup, no bundle encryption/signing.
- [ ] Validation grep catches stale unsupported claims and generated commands are syntax-checked where practical.
- [ ] No code behavior changes are required.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
