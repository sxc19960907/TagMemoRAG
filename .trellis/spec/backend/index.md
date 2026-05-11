# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains the current backend conventions for TagMemoRAG. The project is early-stage, so these rules are derived from the accepted M0 Trellis task:

- `.trellis/tasks/05-10-wave-rag-implementation/prd.md`
- `.trellis/tasks/05-10-wave-rag-implementation/design.md`
- `.trellis/tasks/05-10-wave-rag-implementation/implement.md`

Treat those task files as the detailed product and design contract. Treat this spec directory as the reusable project convention layer that future tasks should load.

---

## Guidelines Index

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
- Read [Directory Structure](./directory-structure.md).
- Read [Quality Guidelines](./quality-guidelines.md).
- If touching persistence, read [Database Guidelines](./database-guidelines.md).
- If touching API responses, rebuild, storage load, or validation, read [Error Handling](./error-handling.md).
- If touching search, rebuild, API, or server startup, read [Logging Guidelines](./logging-guidelines.md).
- Read `.trellis/spec/guides/index.md` and follow the relevant thinking guides.

---

## Core Project Rules

- Keep M0 focused on parser, embedder, graph builder, wave search, anchors, file storage, AppState, API, CLI, and tests.
- Preserve clean dependency direction: entry points call state/storage/algorithm layers; algorithm layers do not call entry points.
- Use JSON+NPZ persistence in M0. Do not use pickle.
- Use stable `anchor_key` for anchors and treat `node_id` as rebuild-local.
- Use structured service errors with `{code, message, detail}`.
- Keep rebuild double-buffer semantics: failed rebuilds preserve the old graph.

---

## Documentation Language

Project spec files are written in English so they can be reused consistently by future AI agents and contributors. Product/task docs may remain bilingual when they need to preserve Chinese domain terms and examples.
