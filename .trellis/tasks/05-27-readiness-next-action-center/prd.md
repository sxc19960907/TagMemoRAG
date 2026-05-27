# Readiness Next Action Center PRD

## Problem

The RAG Readiness dashboard now summarizes whether a KB is ready, but the recommendations are mostly text. Users still need to decide which page to open and what action to take next. This leaves a gap between "I understand the status" and "I can fix or use the system."

## Goal

Turn the dashboard into a guided next-action center. Each readiness state should produce clear, clickable next actions that move the user toward normal RAG Q&A.

## Requirements

- Add action metadata to readiness recommendations: `label`, `href`, `kind`, and optional `primary`.
- Add a single `primary_action` to the summary so the UI can highlight the best next step.
- Map common states to useful actions:
  - KB not loaded -> Manual Library.
  - Manual changes pending or rebuild issues -> Manual Library.
  - No eval report -> Eval Report.
  - Eval failed -> latest report when available, otherwise Eval Report.
  - Ready -> Q&A.
- Render recommendation actions as buttons/links in the dashboard.
- Keep the task read-only; do not add rebuild, eval run, archive, or mutation controls.
- Add a lightweight QA-page readiness callout that links back to the dashboard, without blocking the user from asking questions.

## Acceptance Criteria

- `GET /admin/rag-readiness/summary` returns `primary_action` and action-bearing `recommendations`.
- Recommendations include state-specific links and do not expose raw queries, snippets, vectors, or secrets.
- The dashboard renders a highlighted primary action and per-recommendation action links.
- The QA page shows a lightweight link/callout to check RAG readiness.
- Unit tests cover not-ready, eval-missing, eval-failed/latest-report, and ready primary actions.
- Existing readiness dashboard behavior and navigation remain working.
