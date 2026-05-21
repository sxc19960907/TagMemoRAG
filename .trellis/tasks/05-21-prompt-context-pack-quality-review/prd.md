# Prompt and Context Pack Quality Review

## Goal

Review context packing and answer prompt quality using diagnostics and citation-failure fixtures. Planning only until approved.

## Requirements

- Review context item ordering, citation density, prompt wording, refusal
  behavior, and conflicting evidence handling.
- Use diagnostics/eval evidence rather than prompt taste alone.
- Preserve citation validation and safe answer failure behavior.

## Acceptance Criteria

- [ ] New fixture cases cover citation miss and conflicting evidence.
- [ ] Answer prompt tests and answer API tests are named gates.
- [ ] If live DeepSeek verification is used, env gating and cost controls are
      explicit.
- [ ] Context pack changes are bounded and reversible.
- [ ] Rollback is reverting prompt/context changes.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
