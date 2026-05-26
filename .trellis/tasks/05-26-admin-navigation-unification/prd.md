# Unify admin page navigation

## Goal

Make the browser-first admin pages feel like one coherent RAG control surface by giving each admin page a consistent way to navigate to the other admin pages while preserving the active knowledge-base name.

## Requirements

- Manual Library must link to RAG Workbench, Retrieval Quality, People & Access, and Ask Q&A.
- Retrieval Quality must link to RAG Workbench, Manual Library, People & Access, and Ask Q&A while keeping its existing refresh action.
- People & Access must link to RAG Workbench, Manual Library, Retrieval Quality, and Ask Q&A.
- Navigation links must preserve the current `kb_name` when the page loads and after the KB form changes.
- Keep the change limited to the existing admin page shell; do not add a new global layout system, sidebar, database user model, or backend config mutation.

## Acceptance Criteria

- [x] Every admin page above exposes the expected cross-page links.
- [x] Link `href` values update when the page KB field is changed and loaded.
- [x] Existing primary actions such as rebuild, upload, refresh, and key generation remain present.
- [x] Focused UI/static tests cover the new links and relevant JavaScript link builders.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
