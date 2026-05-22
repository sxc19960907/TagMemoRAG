# Answer intent classification

## Goal

Improve local answer wording by separating answer intent classification from
answer formatting. Generic software documentation questions such as GitHub
workflow/pull-request explanations should use the neutral documentation answer
prefix, while product-manual troubleshooting and safety questions keep the
existing action-oriented prefixes.

This task should also avoid further growth in `api.py` and `cli.py`; changes
belong in the answer layer and focused answer tests.

## Requirements

- Add an answer-layer intent classifier module instead of expanding `api.py` or
  `cli.py`.
- Preserve existing safety and unsupported-repair behavior.
- Preserve product-manual troubleshooting wording for weak steam / "怎么办" /
  fault-style questions.
- Classify generic software documentation questions about workflows,
  pull requests, repositories, README, APIs, and tutorials as generic
  documentation, not troubleshooting.
- Keep the local noop answer generator deterministic.
- Add focused unit tests for both generic documentation and troubleshooting
  intent boundaries.

## Acceptance Criteria

- [ ] GitHub pull-request workflow questions with multiple evidence chunks use
      `根据资料可确认：`, not `建议先这样处理：`.
- [ ] Weak steam / product troubleshooting cases still use `建议先这样处理：`.
- [ ] Safety and unsupported repair tests still pass unchanged.
- [ ] Intent logic lives outside `api.py` and `cli.py`.
- [ ] Existing focused answer and eval tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
