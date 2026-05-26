# RAG quality workflow integration

## Goal

Connect the browser RAG quality loop so users can move naturally between Workbench, Retrieval Quality, Eval Report, and Q&A after seeing a failure or recommendation. The loop should feel like one product workflow rather than separate pages.

## Confirmed Facts

- RAG Workbench links to Manual Library, Retrieval Quality, People, and Q&A, but not Eval Report.
- Retrieval Quality links to Eval Report only after a promotion preview/export exposes `summary.report_path`.
- Eval Report links back to Retrieval Quality, Workbench, and Q&A, but its case cards do not pass the case query back to Q&A or Workbench.
- Q&A currently accepts `kb_name` from the server template but does not prefill a question from query parameters.

## Requirements

- Add a clear Eval Report entry from RAG Workbench so users know where to load generated reports.
- Preserve KB query parameter propagation across Workbench, Retrieval Quality, Eval Report, and Q&A.
- Add case-level actions in Eval Report:
  - open the case query in user Q&A.
  - open the case query in RAG Workbench.
- Add Q&A and Workbench support for a `question` URL query parameter that pre-fills the composer without auto-submitting.
- Keep all links read-only and side-effect-free.
- Support existing Chinese/English UI switching for new labels.

## Acceptance Criteria

- [ ] Workbench route shell and JS include an Eval Report navigation link.
- [ ] Eval Report case cards include Q&A and Workbench links with `kb_name` and `question` query parameters.
- [ ] `/qa?kb_name=default&question=...` pre-fills the Q&A textarea and shows a nonintrusive status message.
- [ ] `/admin/rag-workbench?kb_name=default&question=...` pre-fills the workbench textarea and shows a nonintrusive status message.
- [ ] Unit tests cover shell/static changes and URL parameter behavior where practical.
- [ ] Browser smoke verifies loading a report and following/presenting at least one case action target.
- [ ] Static JS checks and relevant pytest suites pass.

## Out of Scope

- Auto-running Q&A or Workbench questions from URL parameters.
- Running eval jobs in the browser.
- Mutating feedback, eval drafts, or report files from these navigation links.
