# Add Workbench QA navigation

## Goal

Let browser users move from the root RAG Workbench experience to the user-facing Ask Q&A page without manually editing URLs, while preserving the active knowledge-base name.

## Requirements

- RAG Workbench must expose a visible Ask Q&A navigation link next to the existing admin navigation links.
- The Ask Q&A link must include the current `kb_name` on initial render.
- The Ask Q&A link must update when the Workbench KB form is submitted.
- Keep the change limited to the Workbench page shell and existing static link update behavior.

## Acceptance Criteria

- [x] `/admin/rag-workbench?kb_name=<name>` renders an Ask Q&A link with `/qa?kb_name=<name>`.
- [x] Workbench JavaScript updates the Ask Q&A link when the KB is changed.
- [x] Existing Workbench links to Manual Library, Retrieval Quality, and People & Access continue to work.
- [x] Focused UI/static checks cover the link.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
