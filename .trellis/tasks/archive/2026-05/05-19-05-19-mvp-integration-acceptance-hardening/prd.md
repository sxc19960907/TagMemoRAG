# MVP integration acceptance and hardening

## Goal

Prove the shipped MVP/foundation slices work together as a conservative, default-safe system before adding real OCR, visual, connector, or HA/provider work.

## Requirements

- Add integration acceptance coverage that exercises the T1-T9/T1.5 foundations together where practical.
- Preserve default-off behavior for answer generation, OCR, visual retrieval, connectors, reranker, and WAVE experimental features.
- Verify enabled deterministic MVP paths without network or external services.
- Capture the acceptance matrix in task artifacts so future provider tasks know what is proven versus deferred.
- Fix only small defects discovered by the acceptance tests. Large feature gaps should be recorded as follow-up items, not solved here.

## Acceptance Criteria

- [ ] A new acceptance matrix maps T1/T1.5/T2/T3/T5/T6/T7/T8/T9 to concrete tests and known deferred scope.
- [ ] Default Settings keep risky/experimental/provider-backed features off.
- [ ] A deterministic connector-materialized KB can be built, retrieved, answered through noop generation, and logged through QueryPlan without external services.
- [ ] OCR fixture text can enter a KB as normal searchable text when explicitly enabled.
- [ ] Visual manifest candidates can attach or append safe visual evidence when explicitly enabled.
- [ ] Bundle export/import remains a recovery path after deterministic source materialization.
- [ ] Existing focused unit tests and the new acceptance tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
