# RAG delivery readiness checklist

## Goal

Make `/admin/rag-readiness` more useful as a delivery handoff page by adding a browser-visible checklist that explains the key local and production-readiness gates an operator should run before handing the RAG system to another user or environment.

The user should not need to discover release commands from docs or memory. The page should say what each gate proves, when to run it, and the exact command to run, while keeping secrets and local internals out of the UI.

## Confirmed Facts

- `/admin/rag-readiness` already shows KB setup progress, local configuration capability cards, and safe recommendations.
- Existing CLI gates include:
  - `python -m tagmemorag config validate --config <config.yaml>` for local/static config prerequisites.
  - `python -m tagmemorag readiness smoke` for deterministic local RAG composition.
  - `python -m tagmemorag readiness browser-qa` and `--full` for browser-first QA/user-flow checks.
  - `python -m tagmemorag pilot run ...` for retained pre-pilot reports.
  - `python -m tagmemorag production-provider verify --level smoke` for live provider verification.
- Docs already describe RAG quality gates and production environment verification, but the browser readiness page does not surface them as a handoff checklist.
- RAG readiness summary payloads must be additive and safe.
- The page must not display raw secrets, Authorization headers, raw provider responses, document text, storage keys, blob keys, checksums, node ids, local absolute paths, or unbounded eval data.

## Requirements

- Add a `delivery` checklist to `/admin/rag-readiness/summary` with safe, static gate entries.
- Each gate entry must include:
  - stable id
  - title
  - status (`ready`, `needs_review`, or `not_ready`)
  - short summary
  - command string or browser href when useful
  - kind/category suitable for browser display
- Keep the delivery checklist advisory. Missing optional production gates should not change the overall KB readiness status.
- Derive status locally where possible:
  - `config validate` / local smoke / browser QA / pilot report start as `needs_review` because the browser cannot know the last run without retained reports.
  - Live provider verification should be `needs_review` unless local config clearly has a live provider enabled with missing env vars already marked `not_ready` by capability cards.
  - If the KB itself is not loaded, browser QA delivery gate should be `not_ready` because the user flow cannot be meaningfully exercised yet.
- Render the delivery checklist as a distinct browser section after capability cards and before recommendations.
- Add Chinese translations for new visible text.
- Add unit/static and browser coverage.

## Acceptance Criteria

- [x] Summary API returns a `delivery` list with safe static handoff gate entries.
- [x] Browser page renders the delivery checklist with commands/actions users can read.
- [x] The browser delivery section does not expose secrets or unsafe internal identifiers.
- [x] Browser QA delivery gate is `not_ready` when the KB is not loaded.
- [x] Existing readiness status and primary action behavior remain unchanged.
- [x] Static/unit tests cover the payload, renderer, styles, and i18n strings.
- [x] Browser readiness test verifies the delivery checklist appears in a real page.
- [x] Existing unit/e2e non-performance tests remain green.

## Out of Scope

- Running release gates from the browser.
- Persisting gate run history.
- Reading arbitrary local report files from the browser request.
- Live provider calls during page load.
- Editing config files or environment variables from the browser.
- Push to GitHub.
