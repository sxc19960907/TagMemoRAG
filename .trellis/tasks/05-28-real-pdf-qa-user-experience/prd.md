# Real PDF QA user experience acceptance

## Goal

Validate and improve the real browser Q&A experience over real PDF manuals, focusing on answer usefulness, citation/source trust, and source preview ergonomics.

## Requirements

- Use real local PDF manuals from `product_manuals/`.
- Exercise the user-facing `/qa` page in a browser, not only backend APIs.
- Ask realistic maintenance/troubleshooting questions and check that answers use relevant evidence.
- Verify citation chips, source cards, page labels, and source preview links help the user trust the answer.
- Fix issues found during the real browser experience when they are in scope and low-risk.

## Acceptance Criteria

- [x] A browser acceptance flow uploads at least two real PDF manuals and asks realistic questions.
- [x] Answers contain expected real-manual terms and source cards cite the correct PDFs.
- [x] Source previews open as PNG assets without leaking storage keys/blob keys/local paths.
- [x] Any UX issues found are fixed or documented as follow-up if out of scope.
- [x] Focused browser and unit/eval gates pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
