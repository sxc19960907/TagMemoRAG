# General web answer quality

## Goal

Add a checked-in answer-quality diagnostic suite for generic public web
documentation answers. This complements the live-seeded `general_web` retrieval
benchmark by verifying that multi-evidence documentation answers are grounded,
relevant, and citation-supported.

## Requirements

- Add an answer-quality fixture for generic web/software documentation.
- Cover the new neutral multi-evidence answer shape introduced for generic
  questions (`根据资料可确认：`).
- Include at least one multi-evidence grounded answer and one negative case that
  catches an unsupported generic documentation claim.
- Keep the suite static and checked in; do not commit fetched public web
  content.
- Wire the new suite into focused unit/CLI coverage.
- Document how to run it alongside the general web retrieval benchmark.

## Acceptance Criteria

- [ ] `tests/fixtures/answer_quality/general_web.jsonl` contains at least
      three generic documentation cases.
- [ ] `run_answer_quality_diagnostics` passes the new suite.
- [ ] CLI coverage verifies `tagmemorag eval answer-quality --suite
      tests/fixtures/answer_quality/general_web.jsonl`.
- [ ] README includes the command for the general web answer-quality suite.
- [ ] Existing answer-quality tests still pass.
- [ ] No sampled third-party web content is committed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
