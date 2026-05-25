# Manual library to QA user flow

## Goal

Validate and, if needed, repair the normal-user flow from adding a managed manual to rebuilding the KB and asking that new content in QA.

## User Value

A user should not only be able to ask the pre-seeded demo KB. They need a credible path to add or manage a manual, rebuild the KB, and then ask questions against the updated content.

## Confirmed Facts

- The web UI exposes `/admin/manual-library` with upload, bulk import, rebuild, diagnostics, and queue panels.
- API tests already cover `POST /manuals`, `POST /manual-library/rebuild`, library listing, dirty state, and searchable state after rebuild.
- Browser UI tests currently verify page shell/static assets, but not a full upload/rebuild/QA flow.
- The QA page and local demo config are working after the previous task.

## Requirements

- Use the local offline QA demo profile; do not require network services, live LLM providers, Qdrant, S3, or external credentials.
- Validate the manual-library-to-QA path with a new managed manual containing unique content that is not already in the seeded coffee-machine fixture.
- Confirm the system marks the uploaded manual as requiring rebuild, rebuilds it, marks it searchable, and answers a QA question using that new content.
- Prefer minimal fixes if the flow is blocked by UI/API wiring, status reporting, or demo usability.
- Keep generated runtime data under `.tmp/` and out of git.

## Acceptance Criteria

- [x] A managed manual can be uploaded or imported through the local app/API under KB `default`.
- [x] The manual library reports the manual as present and rebuild-required before rebuild.
- [x] A manual-library rebuild completes successfully.
- [x] The rebuilt manual is marked searchable with chunks.
- [x] `/qa` can answer a question that depends on the newly added manual content and renders a cited source.
- [x] Focused tests and/or a recorded browser/API smoke validate the flow.

## Validation Notes

- Added `python -m tagmemorag demo library-qa`, a deterministic local smoke for managed manual upload -> rebuild -> QA.
- Real smoke passed with manual `demo-service-manual`, `searchable=true`, `chunk_count=2`, `pending_changes_after=false`, and QA answer sourced from `demo/demo-service-manual.md`.
- Browser check on `/admin/manual-library?kb_name=default` showed `demo-service-manual`, `yes` searchable, `2` chunks, rebuild `clear`, and no console errors.
- Focused tests passed: `.venv/bin/pytest tests/unit/test_cli.py tests/unit/test_manual_library_api.py tests/unit/test_answer_api.py -q`.

## Out of Scope

- Redesigning the manual-library UI.
- Bulk-import UX polish beyond blockers.
- Live provider onboarding.
- Qdrant/S3/manualslib external import validation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
