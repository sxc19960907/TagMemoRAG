# RAG User Readiness Dashboard PRD

## Problem

TagMemoRAG now has browser-facing QA, RAG Workbench, Manual Library diagnostics, Retrieval Quality, and Eval Report pages. A user can technically experience RAG in the browser, but there is no single place that answers:

- Is this KB ready for normal Q&A?
- If not, what is blocking it?
- Was the latest browser eval good enough?
- Where should I click next to fix or verify the system?

This creates a product gap: features exist, but users still need operator knowledge to understand system state.

## Goal

Add a browser-first readiness dashboard for one KB. The page should summarize core RAG readiness signals and provide clear next actions without requiring CLI commands.

## Confirmed Facts

- `/ready` already reports process-level readiness but returns plain text.
- `/manual-library/diagnostics` already exposes registry, dirty state, rebuild queue, and last rebuild metadata.
- `/eval/suites` already exposes browser-safe eval suites and latest matching browser report metadata.
- `/qa`, `/admin/rag-workbench`, `/admin/manual-library`, `/admin/retrieval-quality`, and `/admin/eval-report` already exist and support `kb_name`.
- Admin pages use Jinja shells plus vanilla JS under `src/tagmemorag/web/static/`.

## Requirements

- Add a new admin page at `/admin/rag-readiness?kb_name=<kb>`.
- Add a JSON endpoint that aggregates safe, bounded readiness signals for the selected KB.
- Display an overall status: `ready`, `needs_review`, or `not_ready`.
- Show cards for KB load/process readiness, manual-library dirty/rebuild state, latest browser eval state, and recommended next actions.
- Provide direct browser links to QA, RAG Workbench, Manual Library, Retrieval Quality, and Eval Report.
- Keep the dashboard read-only; do not trigger rebuilds, eval runs, or data mutations from this task.
- Avoid exposing raw document text, raw queries, vectors, snippets, or secrets.
- Preserve existing page behavior and routes.

## Non-Goals

- No changes to retrieval ranking, answer generation, eval scoring, or feedback promotion.
- No new background jobs or persistent storage.
- No new production dependencies.
- No dashboard writes such as rebuild, archive, or eval-run buttons.

## Acceptance Criteria

- `GET /admin/rag-readiness` serves the browser page.
- `GET /admin/rag-readiness/summary?kb_name=<kb>` returns `schema_version="rag_readiness.v1"` and an overall status with bounded cards/actions.
- For a loaded KB with no dirty manuals and passing latest browser eval, the summary can report `ready`.
- If the KB is not loaded, pending manual changes exist, rebuild jobs failed, or latest browser eval failed, the summary reports a non-ready status with actionable recommendations.
- The Workbench, QA, Manual Library, Retrieval Quality, Eval Report, and People pages include navigation to the dashboard where appropriate.
- Unit tests cover the route shell, static asset, summary API, and key status outcomes.
- Browser smoke confirms the dashboard renders and links to QA/Workbench for the selected KB.
