# First run UI polish

## Goal

Improve the first-run browser experience for a new RAG user by making the empty Manual Library state more guided and by reducing visual overwhelm on the RAG Readiness page.

## Confirmed Facts

- Recent delivery rehearsal found the core flow stable and local delivery gates passing.
- The main non-blocking UX note was that Manual Library's empty state is functional but less guided than the QA first-run panel.
- RAG Readiness currently shows a lot of useful information, but setup, capability, delivery, cards, and recommendations compete for attention.
- The page must remain browser-first and safe: no raw secrets, storage keys, blob keys, checksums, local absolute paths, raw manifest rows, node ids, or document text should be exposed.

## Requirements

- Add a more helpful first-run panel to Manual Library when there are no managed manuals.
  - It should explain the path: upload a manual, rebuild/index it, ask in Q&A.
  - It should make Upload the clear primary action.
  - It should link to RAG Readiness and Q&A for the selected KB.
- Improve RAG Readiness visual hierarchy without changing backend behavior.
  - Make the next best action feel primary but less visually noisy.
  - Make delivery and capability areas easier to scan.
  - Avoid hiding essential readiness signals behind interactions in this slice.
- Preserve existing page routes, IDs, and core tests where possible.
- Add/update static and browser tests for the new first-run panel and readiness layout markers.

## Acceptance Criteria

- [x] Manual Library empty state renders a guided first-run panel for an empty KB.
- [x] The first-run panel has clear Upload, Readiness, and Q&A actions scoped to the current KB.
- [x] RAG Readiness keeps existing information but improves section hierarchy with scoped styling only.
- [x] Browser tests verify the first-run panel is visible in a real Manual Library page.
- [x] Static tests cover new markup/styles/i18n strings.
- [x] Existing unit/e2e non-performance tests remain green.

## Out of Scope

- New backend APIs.
- Running imports or rebuilds automatically.
- Persisting onboarding progress.
- Large redesign of every admin page.
- GitHub push.
