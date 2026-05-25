# Extractive noop demo answers

## Goal

Make the local/offline QA demo feel usable by returning a deterministic, evidence-backed answer instead of the current noop placeholder text.

## Requirements

- The answer provider must remain local, deterministic, and network-free for the demo configuration.
- The noop answer provider should synthesize a concise answer from retrieved evidence/context when allowlisted citations are available.
- Generated citations must continue to use only citation ids that are present in the retrieved allowlist.
- Existing `/answer` and `/qa/answer` response schemas must remain unchanged.
- If no usable evidence text is available, the provider should degrade predictably without inventing unsupported facts.
- Documentation and focused tests must be updated to reflect the extractive noop behavior.

## Acceptance Criteria

- [x] The seeded local QA demo no longer returns `Answer generation is running in noop mode.` for an answerable manual question.
- [x] The generated answer includes readable evidence text and an allowlisted citation.
- [x] Existing answer citation validation still drops invalid citations.
- [x] Focused answer/API/UI tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
