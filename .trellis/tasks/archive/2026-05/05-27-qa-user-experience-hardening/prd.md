# QA User Experience Hardening

## Goal

Harden the browser-first QA page so a normal user can complete ask, read answer, inspect sources, continue, and recover from errors.

## Confirmed Facts

- The user-facing page is `/qa?kb_name=<name>` and it already has a three-pane layout: context/history, answer workspace, and sources.
- The page posts to `/qa/answer`, keeps short session history, can use conversation context for follow-up questions, renders source cards, provides citation chips, supports copy, and submits answer feedback.
- Recent readiness work added a QA-page readiness callout, so this task should improve the QA experience itself rather than adding more admin navigation.
- Existing tests cover shell/static asset wiring and answer API routing, but there is no focused test for the QA page's user guidance surfaces.

## Problem

The QA page is functional, but the real user flow still feels brittle in places:

- Empty and loading states do not clearly describe the full loop of ask, answer, sources, and follow-up.
- Error states only show a generic failed request, leaving users unsure whether to retry, check readiness, or rephrase.
- Source cards exist, but the page does not make it obvious how citations and sources work together.
- Follow-up/context behavior is present but easy to miss.

This matters because the system's readiness/admin pages now guide operators well; the next product risk is whether a normal user can comfortably experience RAG from the browser page.

## Requirements

- Improve the QA page's first-screen guidance without turning it into a marketing/landing page.
- Preserve the direct ask-first workflow; the textarea and Ask button remain the primary action.
- Make pending/loading state clearer and stable while `/qa/answer` runs.
- Make request failures actionable with visible retry/rephrase/readiness guidance.
- Make citations and source cards easier to understand from the answer view.
- Make follow-up/context behavior clearer when a follow-up is available or applied.
- Keep the task browser-first and read-only except for the existing answer request and existing feedback submission.
- Preserve existing API contracts; do not change retrieval, answer generation, ranking, or rebuild behavior.
- Keep Chinese/English language switching compatible for new visible strings.

## Acceptance Criteria

- [ ] `/qa?kb_name=default` still opens as the primary user-facing RAG page.
- [ ] The empty state explains what kind of question to ask and that answers are grounded in sources, without hiding the composer.
- [ ] During a request, the user sees stable progress guidance and controls are disabled only for the active request.
- [ ] On answer success, citations/source interaction remains available and the source panel communicates how many sources were used.
- [ ] On answer failure, the user sees actionable next steps including retry/rephrase and readiness check guidance.
- [ ] Follow-up/context UI remains available and more understandable to a normal user.
- [ ] New visible strings are covered by i18n mapping.
- [ ] Unit/static tests cover the new QA shell and static wiring.
- [ ] Browser smoke covers ask -> answer -> sources/follow-up visibility on `/qa`.
- [ ] Existing answer API and related UI tests remain green.

## Out of Scope

- Changing retrieval, reranking, answer generation, prompt construction, or eval scoring.
- Adding streaming responses.
- Adding mutation controls such as rebuild, eval run, manual import, or archive from the QA page.
- Replacing the current three-pane QA layout wholesale.
- Adding a new authentication or permission model.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
