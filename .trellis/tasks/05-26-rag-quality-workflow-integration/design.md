# Design: RAG quality workflow integration

## Architecture

This is a browser-flow integration task. It changes only templates/static UI and tests; backend answer/eval/search behavior remains unchanged.

Changed surfaces:

- `rag_workbench.html` / `rag_workbench.js`: add Eval Report navigation and `question` URL prefill.
- `eval_report.js`: add per-case action links to Q&A and Workbench.
- `qa_page.js`: support `question` URL prefill.
- `i18n.js`: add labels/status copy.
- tests: route/static assertions and browser smoke.

## URL Contract

- `kb_name`: existing KB selector parameter, preserved across admin pages.
- `question`: optional user-visible query text used to prefill a composer.
- `report_path`: existing eval report path parameter for `/admin/eval-report`.

Prefill is deliberately read-only: pages never auto-submit from URL parameters.

## Flow

1. User opens Workbench and can navigate to Eval Report.
2. User loads report and sees case guidance.
3. User clicks `Ask in Q&A` or `Open in Workbench` on a case.
4. Target page opens with the case query prefilled and a status note explaining that the user can edit and submit.

## Compatibility

Existing links without `question` continue to work. Existing Q&A and Workbench manual entry behavior is unchanged.
