# RAG delivery rehearsal

## Goal

Experience the current RAG system as a user/operator would before handoff: open the browser readiness page, follow the delivery checklist, run the local gates that are safe in this environment, and fix any small issues found during the rehearsal.

## Requirements

- Start from a clean working tree.
- Use the browser-facing pages where possible, especially `/admin/rag-readiness` and `/qa`.
- Run safe local delivery gates:
  - `config validate`
  - `readiness smoke`
  - `readiness browser-qa`
- Do not run live provider verification unless explicitly configured and safe; this task is a local rehearsal.
- Capture any UX or functional issue discovered.
- Fix bounded issues directly if they are small and covered by tests; split larger issues into future tasks.
- Preserve the current stability bar with focused tests and the broader non-performance gate if code changes are made.

## Acceptance Criteria

- [x] RAG readiness page opens in the in-app browser and the handoff checklist is understandable.
- [x] Local config validation gate result is recorded.
- [x] Local readiness smoke gate result is recorded.
- [x] Browser QA readiness gate result is recorded.
- [x] Any small issue found is either fixed with tests or explicitly documented as follow-up.
- [x] Work is committed, archived, and journaled if changes are made.

## Out of Scope

- Live provider verification.
- GitHub push.
- Deployment to a remote host.
