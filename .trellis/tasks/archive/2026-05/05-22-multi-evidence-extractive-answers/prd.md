# Multi evidence extractive answers

## Goal

Improve the local/offline noop answer provider so answerable questions can use multiple retrieved evidence items instead of copying only the first supported excerpt.

## Requirements

- The provider must remain deterministic, local, and network-free.
- The `/answer` and `/qa/answer` schemas must remain unchanged.
- The provider should select a small bounded set of allowlisted evidence/context excerpts, deduplicate near-identical text, and preserve retrieval order.
- Each included claim/excerpt must carry its own exact allowlisted citation id.
- The output should be readable as a compact answer for the user page, not a raw dump of all retrieval results.
- If only one supported excerpt exists, current single-excerpt behavior should continue.
- If no supported excerpt exists, the provider should keep the insufficient-evidence fallback.

## Acceptance Criteria

- [x] Unit tests cover multi-evidence synthesis, citation ordering, deduplication, and single/no-evidence fallbacks.
- [x] `/answer` and `/qa/answer` continue to return `answer.kind="answer"` with valid citations for the seeded demo.
- [x] The seeded demo answer for `蒸汽很小怎么办？` includes both the primary steam guidance and an additional relevant maintenance/cleaning clue when retrieved.
- [x] Focused answer/API/UI tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
