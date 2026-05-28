# Real PDF preview browser acceptance

## Goal

Validate the PDF source preview feature with a real local PDF and the real browser UI, not only mocked assets or synthetic unit tests.

## Requirements

- Install the optional `pdf-preview` dependency group in the project environment.
- Use a real PDF from `product_manuals/` when available.
- Exercise the browser path end to end: upload PDF, rebuild, ask in Q&A, click/open source preview.
- Verify the preview response is a rendered PNG from `/assets/{asset_id}` and user-facing source UI remains safe.
- If real experience issues appear, fix them before closing the task.

## Acceptance Criteria

- [x] PyMuPDF/`fitz` is importable in the project environment.
- [x] Config validation for enabled PDF previews no longer reports the missing PyMuPDF warning.
- [x] A real PDF browser flow reaches Q&A and opens a source preview PNG.
- [x] Any UI or backend issues found during real use are fixed or explicitly documented if out of scope.
- [x] Relevant tests pass after the real validation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
