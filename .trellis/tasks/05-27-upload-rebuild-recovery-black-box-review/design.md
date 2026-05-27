# Upload Rebuild Recovery Black Box Review Design

## Scope

This task reviews and hardens the browser-first recovery path around Manual Library uploads and rebuilds. The primary surface is `/admin/manual-library`.

## Current Data Flow

Successful upload with rebuild:

`Upload dialog -> POST /manuals -> rebuild_task or rebuild_job -> poll status -> Manual table -> Q&A`

Pending upload without rebuild:

`Upload dialog -> POST /manuals -> manual.rebuild_required=true -> dirty summary + Next step -> operator clicks Rebuild`

Failed rebuild:

`POST /manual-library/rebuild or queued job -> poll terminal failed status -> status strip + diagnostics/recommendations + queue actions`

## Risk Controls

- The page should never imply a dirty or failed rebuild KB is ready for normal Q&A.
- Failed rebuild messaging must say that existing served KB remains active when applicable.
- Retry should use the existing queue retry or rebuild button; no new backend state is needed for this pass.
- Error messages should stay structured and sanitized per `.trellis/spec/backend/error-handling.md`.

## Implementation Direction

Start with black-box review and tests. If existing UI lacks a clear recovery route, add small frontend-only guidance:

- a failed rebuild next-step state;
- clearer status copy for immediate and queued rebuild failures;
- i18n strings and tests for visible guidance.
