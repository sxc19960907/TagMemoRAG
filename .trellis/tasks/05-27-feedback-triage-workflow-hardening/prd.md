# Feedback Triage Workflow Hardening

## Goal

Make the Retrieval Quality page easier to use during a small RAG trial by turning raw feedback records into clear triage decisions. Operators should be able to understand whether a case needs expected evidence, can be marked triaged, should be dismissed, or is ready to preview/export as an eval draft without reading implementation details.

## Requirements

- Keep the existing feedback API and persisted status model (`new`, `triaged`, `promoted`, `dismissed`) unchanged.
- Add browser-visible next-action guidance in the selected feedback detail pane.
- Surface low-risk quick actions for common operator decisions, especially marking a reviewed case as `triaged`.
- Preserve the existing promotion preview/export behavior and its readiness criteria.
- Keep the page usable in both English and Chinese UI modes where labels are managed by the shared i18n layer.
- Update operator documentation if the triage flow changes.

## Acceptance Criteria

- [ ] Retrieval Quality shows a clear next-action panel for selected feedback.
- [ ] Not-helpful feedback without expected evidence tells the operator to add expected evidence before promotion.
- [ ] Feedback with expected evidence is presented as ready to preview/export.
- [ ] Dismissed feedback is clearly shown as excluded from promotion.
- [ ] A quick action can mark the selected case as `triaged` through the existing review API.
- [ ] Existing browser feedback-to-eval flow remains covered by tests.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
