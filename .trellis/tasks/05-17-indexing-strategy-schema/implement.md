# Implementation Plan — Indexing Strategy and Index Schema

## Scope

This task is complete when the indexing strategy contract is documented and validated against the architecture roadmap. Runtime indexing behavior should not change in this task.

## Checklist

- [x] Write PRD with goal, requirements, production readiness, and out-of-scope.
- [x] Write ID full-map in `design.md`.
- [x] Write current/future index inventory.
- [x] Write object participation matrix.
- [x] Write Qdrant payload schema direction and point-id migration stance.
- [x] Write conservative hybrid fusion plan and future exploration plan.
- [x] Write incremental rebuild reuse/refresh rules.
- [x] Write debug/observability contract.
- [x] Write eval gates for future index changes.
- [x] Run Trellis validation.
- [x] Confirm no runtime code changes were made.

## Validation

```bash
.venv/bin/python .trellis/scripts/task.py validate .trellis/tasks/05-17-indexing-strategy-schema
git diff --check
git status --short
```

Validation completed:

- `.venv/bin/python .trellis/scripts/task.py validate .trellis/tasks/05-17-indexing-strategy-schema`
- `git diff --check`
- `git status --short`

## Direction Gate

- **Gate A**: This task prepares Phase 3 but does not implement `/retrieve`.
- **Gate B**: Current `/search`, graph, Qdrant, and chunk identity behavior remain unchanged.
- **Gate C**: Future work is broken into PR-sized follow-up tasks.

Gate result:

- Passed. This task only adds Trellis task documentation and does not modify runtime code.
