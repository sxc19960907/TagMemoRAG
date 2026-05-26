# RAG feedback eval closure

## Goal

Backfill an honest Trellis closure record for the completed browser RAG feedback-to-eval loop work.

This task was created after the implementation because the user explicitly asked whether Trellis had been followed. The implementation was completed as spec-guided inline work on `master`; this record preserves the requirements, outcome, validation, and follow-up plan so later Trellis sessions have a durable handoff.

## Requirements

- Connect Q&A page answer feedback to the existing retrieval feedback store without introducing a parallel persistence path.
- Make Retrieval Quality usable as a review workspace for Q&A/Search/Retrieve feedback, including source classification, selected/expected evidence, trace/build/plan detail, and review guidance.
- Make promotion preview explain export readiness, skipped reasons, and next actions.
- Allow expected evidence to be filled from selected evidence or manual fields in the browser, saved through the review overlay, and used by promotion preview/export.
- Surface exported eval draft path and the command needed to run the generated suite.
- Verify browser-first user flows, not only API/CLI paths.
- Preserve existing storage contracts: raw feedback remains JSONL, review changes live in the review overlay, and exported eval cases remain JSONL compatible with the existing eval loader.

## Acceptance Criteria

- [x] Q&A `Helpful` / `Not helpful` feedback posts to `/search/feedback` and appears in Retrieval Quality.
- [x] Retrieval Quality shows feedback summary, source label, selected evidence, expected evidence, readiness guidance, and promotion preview cards.
- [x] Expected evidence can be added from the browser and changes preview from `NEEDS INPUT` to `READY`.
- [x] Export writes a parseable eval JSONL case and marks feedback as `promoted`.
- [x] The UI shows the eval draft output path and a next command for running the generated suite.
- [x] Focused unit/static/browser checks pass.

## Outcome

Implemented and pushed on `master` across these commits:

| Hash | Message |
|------|---------|
| `6c4a40f` | Connect QA feedback to retrieval quality |
| `1c26c6d` | Polish retrieval quality review workspace |
| `09f88fa` | Clarify feedback promotion readiness |
| `1adf7c6` | Enable expected evidence editing |
| `eaf9fc8` | Surface exported eval draft guidance |

The resulting browser workflow is:

1. User asks a Q&A question.
2. User clicks `Not helpful`.
3. Retrieval Quality receives the feedback.
4. Operator reviews selected evidence.
5. Operator fills expected evidence from selected evidence or manual fields.
6. Promotion preview changes from `NEEDS INPUT` to `READY`.
7. Export writes an eval draft JSONL case.
8. Feedback status becomes `promoted`.

## Validation

- `node --check src/tagmemorag/web/static/qa_page.js`
- `node --check src/tagmemorag/web/static/retrieval_quality.js`
- `node --check src/tagmemorag/web/static/i18n.js`
- `uv run pytest tests/unit/test_retrieval_feedback.py tests/unit/test_queryplan_feedback_plan_id.py tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_admin_ui_browser_workflows`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow`
- `git diff --check`

Unit coverage additionally verifies exported feedback eval drafts are parseable by `tagmemorag.eval.dataset.load_eval_suite`.

## Follow-Up

- Run a broader full-suite CI pass before starting the next feature if there is time.
- Consider adding a visible "Run eval" workflow or docs around `tagmemorag eval run --suite <path>`.
- Consider a future bulk workflow for multiple feedback rows once single-row review remains stable.

## Notes

- This is a backfilled Trellis closure record, not evidence that Phase 1 planning happened before implementation.
