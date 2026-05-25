# Stepwise QA answer UX

## Goal

Make `/qa` answers easier for end users to act on by formatting grounded responses as a short recommendation followed by numbered steps with citations.

## Requirements

- Keep the existing `/answer` and `/qa/answer` response schemas unchanged.
- The offline/noop answer provider must remain deterministic, local, and evidence-only.
- Multi-evidence answers should render as a concise introductory recommendation plus numbered actionable steps.
- Each step must keep the exact allowlisted citation id for the evidence it uses.
- Single-evidence answers should remain readable and cited.
- The user page should safely render line breaks and numbered steps while preserving clickable citation chips.
- The user page must continue to hide debug identifiers and KB selection controls.

## Acceptance Criteria

- [x] Noop answer generator tests assert stepwise multi-evidence output and citation ordering.
- [x] QA page rendering tests assert numbered answer formatting and clickable citation support are both present.
- [x] Seeded demo answer for `蒸汽很小怎么办？` displays a recommendation and numbered steps with clickable citation chips.
- [x] Focused answer/API/UI tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
