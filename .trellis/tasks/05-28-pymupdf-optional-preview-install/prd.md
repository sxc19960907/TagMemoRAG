# PyMuPDF optional install for PDF previews

## Goal

Make PDF page preview rendering easy to install and validate without making PyMuPDF a mandatory runtime dependency.

## Requirements

- Add an optional dependency group for PDF preview rendering.
- Improve config validation messaging so operators know the exact install command when PyMuPDF is missing.
- Update user-facing setup docs for enabling PDF page previews.
- Preserve default install behavior; normal search, Q&A, and CI must not require PyMuPDF.
- Verify the optional happy path when the dependency is installed or skip cleanly when it is absent.

## Acceptance Criteria

- [x] `pyproject.toml` exposes a clear optional extra for PDF preview rendering.
- [x] `config validate` reports a safe install hint when `assets.pdf_page_snapshots_enabled=true` but PyMuPDF is absent.
- [x] README documents the optional install command and config flags.
- [x] Tests cover the dependency hint and existing PDF preview behavior.
- [x] Browser success-path test remains optional and skips clearly without PyMuPDF.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
