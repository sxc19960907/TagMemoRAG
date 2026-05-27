# User-facing RAG Conversation Experience Design

## Existing Facts

- `/qa` renders `qa_page.html` and `qa_page.js`.
- The Q&A page already supports session-backed conversation turns, follow-up context, source cards, feedback submission, KB selection, and i18n.
- Manual ingestion is already implemented through `/manuals`, `/manuals/validate`, `/manual-library/rebuild`, `/manual-library/rebuild-jobs/*`, `/manual-library`, and `/manual-library/diagnostics`.
- Browser integration already proves the admin Manual Library upload/rebuild path can lead into Q&A.

## Scope

Add a focused Q&A-page intake panel that wraps the existing manual-library APIs for the small-trial happy path:

1. Choose a file.
2. Review metadata defaults.
3. Validate/upload with `trigger_rebuild=true`.
4. Poll rebuild task/job status.
5. Show ready state and keep the user on the Q&A page to ask.

The admin Manual Library remains the full operations surface for bulk import, tag governance, replacement, deletion, audit, and recovery.

## Frontend Contract

`qa_page.html` gains a compact intake card in the left rail:

- file input
- title, source file, product category, language, tags
- validate/upload button
- status/messages area
- advanced link to Manual Library

`qa_page.js` owns the page state:

- derive defaults from the selected filename
- POST `/manuals/validate`
- POST `/manuals` with multipart `file`, `metadata`, `kb_name`, `overwrite=false`, `trigger_rebuild=true`
- poll returned `rebuild_task.task_id` or `rebuild_job.job_id`
- refresh KB options after upload/rebuild
- show a ready-to-ask status and keep composer focus available

No new backend route is required unless existing API gaps appear during implementation.

## API/Backend Contract

Reuse existing structured errors and manual-library rebuild semantics:

- Validation errors remain `{code, message, detail}` and are rendered as user-facing messages.
- Rebuild failures must preserve the old graph through the existing double-buffer semantics.
- Auth and KB allowlist behavior remain enforced by current dependencies.

## i18n

Add all new visible strings to `i18n.js`. Existing page translation should cover the new panel through the same `initI18n`/`translatePage` path.

## Testing

- Unit/static tests verify Q&A template includes the intake UI and JS references existing manual-library endpoints.
- Browser integration adds a QA-first upload/rebuild/question flow.
- Existing browser Q&A tests must continue to pass.

## Tradeoffs

- This task deliberately uses a metadata form instead of drag-and-drop plus auto-tagging. That keeps the first iteration deterministic and aligned with current validation.
- This task does not add server-persisted chat history. Existing session storage is sufficient for the trial-user flow and avoids new persistence/privacy decisions.
