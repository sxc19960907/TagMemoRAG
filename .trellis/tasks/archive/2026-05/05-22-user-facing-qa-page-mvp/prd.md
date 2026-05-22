# User-facing QA page MVP

## Goal

Add a simple user-facing question-answer page that lets non-admin users ask a product-manual question, read the answer, and see the cited sources without exposing RAG diagnostics.

This is a product-experience pivot from the admin-only RAG Workbench. The Workbench remains the debugging surface; this page becomes the clean first screen for a normal user.

## Requirements

- Serve a new non-admin page at `GET /qa`, with `?kb_name=...` support matching existing admin pages.
- Reuse the existing `/answer` API instead of adding a new answer contract.
- Hide internal diagnostics such as plan ids, build ids, answerability internals, top-k controls, source-k controls, and raw retrieval results.
- Show only the user-relevant flow: question input, ask button, answer/refusal/error state, and cited sources.
- Keep API token handling available for authenticated deployments, but visually secondary.
- Use the existing server-rendered Jinja2 + vanilla JS + shared static asset pattern; do not add a frontend build step.
- Keep the RAG Workbench available as the admin/debugging page.

## Acceptance Criteria

- [x] `GET /qa?kb_name=ops` returns an HTML shell with the selected KB in page config.
- [x] The page submits questions to `POST /answer` with `include_retrieve=true`, `top_k=5`, `source_k=8`, and mode `classic`.
- [x] Successful answers render the answer text and visible citation/source items.
- [x] Refusals and request failures render user-readable messages without exposing trace/build/plan internals.
- [x] Existing admin pages and static assets continue to load.
- [x] Focused UI tests cover the new route and static JavaScript asset.

## Notes

- Lightweight task: PRD-only is sufficient because it reuses the existing `/answer` backend contract and UI asset pattern.
- Out of scope: chat history, streaming answers, feedback collection, KB picker from `/kb`, document preview, and redesigning admin pages.
