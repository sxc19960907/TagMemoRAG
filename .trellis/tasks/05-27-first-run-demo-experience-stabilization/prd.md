# First Run Demo Experience Stabilization

## Goal

Align the browser QA first-run demo, suggested questions, seed manuals, and tests so a normal user can ask realistic questions and receive useful grounded answers with sources.

## User Value

A user who opens the QA page for the first time should be able to click or type the visible suggested questions and see answers that match the demo manual domain. The first impression should be a product-manual RAG experience, not an internal service-mode demo.

## Confirmed Facts

- `/qa?kb_name=default` currently suggests coffee-machine troubleshooting questions such as weak steam, no coffee output, descaling, and nozzle cleaning.
- `tests/fixtures/coffee_machine.md` already contains grounded content for these questions.
- `tagmemorag demo library-qa` currently seeds a `demo-service-manual` with service-mode content and defaults to `服务模式怎么进入？`.
- The browser test currently verifies the service-mode path, which conflicts with the user-facing QA first-run suggestions.

## Requirements

- Change the library QA demo seed so it represents the same coffee-machine troubleshooting domain shown by the QA page.
- Keep the existing demo/manual-library upload and rebuild path intact.
- Update tests so the browser user flow validates a realistic first-run QA question.
- Avoid changing API contracts unless required.
- Preserve backwards compatibility where reasonable for scripts or tests that reference `demo-service-manual`.

## Acceptance Criteria

- [ ] The default `tagmemorag demo library-qa` question aligns with the QA page's suggested questions.
- [ ] Demo seeded manual content can answer at least weak steam, no coffee output, descaling, and nozzle cleaning questions.
- [ ] Browser QA flow test asks a first-run suggested question and verifies a grounded answer and source.
- [ ] Existing unit/static checks and the affected browser opt-in test pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
