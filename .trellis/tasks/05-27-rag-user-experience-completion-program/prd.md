# RAG User Experience Completion Program

## Goal

Long-running task tree to bring TagMemoRAG from admin-ready to a stable browser-first RAG experience for normal users.

## User Value

TagMemoRAG should feel usable from the browser without requiring command-line knowledge. A normal user should be able to open the QA page, understand what knowledge base is being used, ask realistic questions, see grounded answers with sources, recover from empty or weak answers, and trust that the system remains stable as RAG features grow.

## Confirmed Facts

- The project already has a browser-first QA page at `/qa?kb_name=default`.
- Recent work added QA UX hardening and browser regression smoke coverage.
- The current first-run demo path is not yet fully aligned with the QA page's suggested questions: weak-steam questions can retrieve less helpful service-mode content in some demo flows.
- The repository already contains strong coffee-machine fixtures for retrieval, answer quality, and browser tests.
- GitHub push is intentionally deferred until network conditions recover.

## Requirements

- Manage this as a parent task with independently verifiable child tasks.
- Keep every child task tied to a real browser/user outcome, not only command-line behavior.
- Preserve system stability by running focused unit tests, static checks, and browser opt-in checks for affected surfaces.
- Archive completed child tasks so finished work does not pollute later planning.
- Do not push to GitHub during this program until the user says the network is ready or explicitly asks to retry.
- Record session progress in the Trellis journal after substantial completed work.

## Child Task Roadmap

1. First-run/demo experience stabilization
2. Browser-first QA readiness quality gate
3. Test tier and quality-gate documentation
4. User-facing knowledge-base selection and multi-KB clarity
5. Feedback-to-eval loop smoothing
6. Deployment/pilot readiness pass
7. Integrated black-box user acceptance review

## Cross-Child Acceptance Criteria

- [x] A new user can open `/qa?kb_name=default` and get useful grounded answers for at least three realistic suggested questions.
- [x] QA answers show clear source evidence or clear recovery actions when evidence is insufficient.
- [x] Browser tests cover the most important normal-user QA journey.
- [x] Admin/workbench flows remain compatible with user-facing QA changes.
- [x] Test commands and readiness checks are documented enough for future sessions to continue reliably.
- [x] Completed child tasks are archived and journaled.
- [x] The final program includes a black-box browser acceptance pass from the user perspective.

## Acceptance Criteria

- [x] All roadmap child tasks are completed or deliberately deferred with a written reason.
- [x] The user-facing QA experience is stable enough for a normal browser-based RAG trial.
- [x] The final verification suite passes locally, including the relevant browser UI checks.
- [x] Network-dependent GitHub push remains deferred unless explicitly resumed by the user.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
