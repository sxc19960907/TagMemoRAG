# RAG Workbench MVP

## Goal

Create a usable browser workbench for asking questions against a KB, seeing the
generated answer, inspecting cited evidence, and navigating to existing manual
management and retrieval-quality tools.

## User Value

The backend now has ingestion, retrieval, `/answer`, QueryPlan, evidence,
feedback, and operator pages. A workbench turns those capabilities into a
single product-facing experience instead of requiring CLI/curl/API knowledge.

## Confirmed Facts

- Existing operator pages live under `/admin/manual-library` and
  `/admin/retrieval-quality`.
- Existing static assets are served from `/static/manual-library/...`.
- `/answer` returns answer payload plus optional retrieve payload, evidence,
  citations, warnings, plan id, and build id.
- `/answer` works in noop mode for local/offline testing and returns safe error
  payloads when generation is disabled or fails.
- Existing UI tests cover template shells and static assets with FastAPI
  `TestClient`.

## Requirements

- Add `/admin/rag-workbench?kb_name=...` as an admin HTML shell.
- The page must let the user set KB, optional API token, question, `top_k`, and
  `source_k`.
- Submitting a question calls `/answer` with `include_retrieve=true`.
- The page must render:
  - answer kind/text/refusal reason;
  - answer citations;
  - evidence/context results from the retrieve payload;
  - warnings, plan id, build id, and answerability summary.
- The page must include navigation links to Manual Library and Retrieval
  Quality for the selected KB.
- The UI must handle loading, success, refusal, and error states without
  requiring a page reload.
- Static assets must be tested and served by FastAPI.
- No new frontend framework or build step.

## Acceptance Criteria

- [x] `/admin/rag-workbench` serves an HTML shell with KB, token, question, and
      answer/evidence containers.
- [x] `rag_workbench.js` calls `/answer` with `kb_name`, `question`, `top_k`,
      `source_k`, and `include_retrieve=true`.
- [x] The UI renders answer text/refusal/error, citations, warnings, plan id,
      build id, and retrieve evidence/results.
- [x] The UI has links to manual-library and retrieval-quality pages for the
      selected KB.
- [x] Unit tests cover route shell and static JS/CSS references.
- [x] Existing answer API tests remain green.

## Out of Scope

- Multi-turn conversation memory.
- Streaming answer tokens.
- Upload or bulk import redesign.
- Live-provider-specific UI controls.
- New authentication storage; token remains a local input like existing admin
  pages.

## Rollback

Remove the route, template, JS/CSS additions, and tests. Backend API behavior
remains unchanged.
