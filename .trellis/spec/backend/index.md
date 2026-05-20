# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Primary Source

The single authoritative source for system architecture is the living document:

- **[Architecture (living doc)](./architecture.md)** — Phase 0–5 contracts (with v2 revisions), Phase 6–8 blueprints, cross-cutting principles, follow-up execution roadmap, and reference implementations.

Read this document first when starting backend work.

---

## Per-topic Conventions

This directory contains the reusable backend conventions. The architecture doc above is the source of truth for system shape; the guides below are detailed conventions for specific concerns.

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization, dependency direction, naming | Current |
| [Database Guidelines](./database-guidelines.md) | File-backed storage, schema, atomic writes | Current |
| [Error Handling](./error-handling.md) | Service errors and API response shape | Current |
| [Quality Guidelines](./quality-guidelines.md) | Testing, forbidden patterns, review checklist | Current |
| [Logging Guidelines](./logging-guidelines.md) | M0 logging fields and future observability hooks | Current |

---

## Pre-Development Checklist

Before changing backend code or task docs:

- Read the active task PRD/design/implement files.
- Read [Architecture (living doc)](./architecture.md) for the relevant section (A / B / C).
- Read [Directory Structure](./directory-structure.md).
- Read [Quality Guidelines](./quality-guidelines.md).
- If touching persistence, read [Database Guidelines](./database-guidelines.md).
- If touching API responses, rebuild, storage load, or validation, read [Error Handling](./error-handling.md).
- If touching search, rebuild, API, or server startup, read [Logging Guidelines](./logging-guidelines.md).
- Read `.trellis/spec/guides/index.md` and follow the relevant thinking guides.

---

## Core Project Rules

These rules are reaffirmed by the living architecture doc; refer to it for the design rationale.

- Preserve clean dependency direction: entry points call state/storage/algorithm layers; algorithm layers do not call entry points.
- Use JSON+NPZ persistence by default; SQLite for QueryPlan persistence; no pickle.
- Use stable `anchor_key` for anchors and treat `node_id` as rebuild-local.
- Use structured service errors with `{code, message, detail}`.
- Preserve rebuild double-buffer semantics: failed rebuilds preserve the old graph. Generation-aware rebuild (A4 in the architecture doc) is the next step here.

---

## Documentation Language

Project spec files are written in English so they can be reused consistently by future AI agents and contributors. Product/task docs may remain bilingual when they need to preserve Chinese domain terms and examples.

---

## Historical References

The following archived task documents informed the current architecture. They are preserved for historical context but are no longer authoritative — any conflict is resolved by the living architecture doc above.

- `.trellis/tasks/archive/2026-05/05-10-wave-rag-implementation/` — original M0 implementation task
- `.trellis/tasks/archive/2026-05/05-17-production-rag-architecture/design.md` — predecessor architecture document, superseded by `architecture.md` v2 on 2026-05-17
- `.trellis/tasks/archive/2026-05/05-17-wave-readiness-flags/` — empirical evaluation that produced the WAVE 3/3 KEEP_OFF result referenced in A5
