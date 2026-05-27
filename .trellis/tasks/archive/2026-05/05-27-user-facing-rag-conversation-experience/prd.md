# User-facing RAG conversation experience

## Goal

Make the browser Q&A page usable as the normal user's primary RAG entry point, including a lightweight path to add a manual and continue into Q&A without visiting the admin manual-library page first.

The existing `/qa?kb_name=...` page already has conversation history, follow-up context, source cards, feedback, KB selection, and language switching. This task should extend that experience instead of rebuilding it.

## Requirements

- Add a user-facing document intake panel on the Q&A page for small/manual trial use.
- Let a user upload a manual from the Q&A page with the minimum metadata needed by the existing manual-library API.
- Reuse the existing `/manuals`, `/manuals/validate`, `/manual-library/rebuild`, and rebuild-job APIs; do not create a parallel ingestion backend.
- Prefer sensible metadata defaults derived from the selected file name and active KB, while still letting the user edit title, category, language, tags, and source path.
- Support automatic rebuild after upload and surface progress/status in Q&A terms: uploaded, indexing, ready to ask, needs attention.
- Preserve auth behavior: when auth is enabled, uploads use the shared browser token and require the existing manual-library/rebuild scopes.
- Preserve existing Q&A behavior: asking, follow-up context, citation source focus, feedback, KB switching, and language switching must continue to work.
- Keep admin-only deep controls in Manual Library; the Q&A page should expose a focused first-run/trial path, not bulk import, tag governance, hard delete, or audit tooling.

## Acceptance Criteria

- [ ] `/qa?kb_name=default` shows a compact "Add manual" path understandable to a non-admin trial user.
- [ ] A user can select a `.md`/text manual, review/edit generated metadata, upload it, trigger indexing, and ask a grounded question from the same QA page.
- [ ] Upload validation errors are visible on the QA page with actionable field-level text.
- [ ] Rebuild or queued rebuild progress is visible until ready, failed, or timed out; the old KB is not cleared by failure.
- [ ] The page links to Manual Library/RAG Readiness for advanced recovery without requiring that route for the happy path.
- [ ] The new UI is translated by the existing English/Chinese language switcher.
- [ ] Browser integration covers upload -> rebuild -> Q&A from the QA page.
- [ ] Focused unit/static checks and browser QA readiness pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
