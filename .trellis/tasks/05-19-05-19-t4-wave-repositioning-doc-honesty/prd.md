# T4 WAVE repositioning documentation honesty patch

## Goal

Bring operator-facing docs and code-level descriptions into alignment with architecture A5/C10: WAVE remains buildable research code, but it is experimental, default-off, and not part of the critical retrieval path unless explicitly enabled.

## Requirements

- Remove self-applied "production-grade" wording from operator-facing documentation.
- Reposition README overview language so TagMemoRAG is described by its currently enabled retrieval stack, not by WAVE as the default product identity.
- Document WAVE Phase 0/1 as experimental/default-off extensions with the archived KEEP_OFF evaluation context.
- Update code-level docstrings/comments that present Phase 4 geodesic rerank as a production path rather than an experimental default-off feature.
- Preserve existing runtime behavior and public API shapes.

## Acceptance Criteria

- [ ] `README.md` does not use "production-grade" as a self-label.
- [ ] README overview and operator sections state that WAVE Phase 0/1 features are default-off experimental additions.
- [ ] WAVE-related code docstrings/comments mention experimental/default-off status where they describe Phase 1/Phase 4 behavior.
- [ ] Architecture spec records T4 as shipped after implementation.
- [ ] Validation grep and focused tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
