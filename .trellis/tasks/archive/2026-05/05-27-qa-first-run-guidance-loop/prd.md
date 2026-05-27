# QA first-run guidance loop

## Goal

Improve the normal user's first-run Q&A path so an empty or newly uploaded knowledge base guides the user toward the next useful action instead of leaving them to infer the workflow.

## Requirements

- When the active KB is empty or not loaded, the Q&A page should foreground adding a manual before asking.
- After a manual is uploaded and indexed from the Q&A page, the page should offer useful suggested questions derived from the uploaded metadata.
- If indexing fails from the Q&A page, the page should provide clear recovery links/actions to RAG Readiness and Manual Library.
- Preserve existing Q&A asking, follow-up, source focus, feedback, KB switching, language switching, and upload behavior.
- Reuse existing frontend/API contracts; do not add a parallel backend.

## Acceptance Criteria

- [ ] First-run `/qa?kb_name=default` with no built KB shows upload-first guidance in the answer workspace.
- [ ] Empty/not-ready state still allows asking, but makes the upload path visually and textually clear.
- [ ] Successful QA-page upload/index updates suggested questions and exposes them as clickable prompts.
- [ ] Indexing failure shows recovery actions linking to RAG Readiness and Manual Library for the active KB.
- [ ] New copy participates in the existing English/Chinese switcher.
- [ ] Browser integration covers first-run guidance and upload-derived suggestions.
- [ ] Focused static/unit/browser checks pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
