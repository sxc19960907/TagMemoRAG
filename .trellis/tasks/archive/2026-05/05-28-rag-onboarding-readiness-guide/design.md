# RAG Onboarding Readiness Guide Design

## Scope

This task upgrades the existing `/admin/rag-readiness` browser page into an onboarding guide. It keeps the current API and server routes intact, using the existing `rag_readiness.v1` summary as the source of truth.

## Information Architecture

The page should render in this order:

1. Topbar with KB selector, token field, language switcher, and compact navigation.
2. Onboarding hero:
   - status pill
   - title and summary
   - selected KB
   - primary action button
   - secondary refresh/open actions
3. Progress guide:
   - Load knowledge base
   - Index manuals
   - Review retrieval quality
   - Start Q&A
4. Readiness cards:
   - KB Loaded
   - Manual Library
   - Retrieval Eval
   - User Q&A
5. Recommended tasks:
   - one row per recommendation
   - severity, short action text, direct link

## Rendering Strategy

No new frontend framework is introduced. `rag_readiness.js` will:

- transform summary cards into a small view model
- derive progress steps from existing card ids/statuses
- render state-specific copy through `t(...)`
- keep links synced to `kb_name`
- keep raw detail display bounded to a curated list of safe fields

`manual_library.css` will keep shared admin tokens and add a more refined readiness-specific layout:

- full-width bands/sections rather than nested cards
- compact cards with 8px radius
- status colors using green/amber/red/blue neutrals, avoiding one-note color palettes
- responsive layout for desktop and mobile widths

## Safety

The UI must not render unsafe internal values. Detail rows should be limited to human-readable fields already exposed by the summary API:

- loaded/node counts/build id are allowed because existing readiness already displays them; do not add lower-level ids
- manual dirty counts, job counts, source-preview status/message, page snapshot counts
- eval case/failure counts

Do not render arbitrary nested objects.

## Compatibility

- Existing URL remains `/admin/rag-readiness?kb_name=...`.
- Existing summary API remains compatible.
- Existing tests that search for old headings should continue or be updated to the improved visible text.
- Language switching should continue to mount globally via `initI18n`.

## Validation

Use browser integration because the primary deliverable is a user-facing page. Keep exact visual assertions stable by checking semantic presence, responsive layout metrics, action links, and absence of obvious internal leaks rather than pixel-perfect snapshots.
