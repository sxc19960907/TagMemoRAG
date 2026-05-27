# Feedback Triage Workflow Hardening Design

## Scope

This task is a UI/workflow hardening pass for `/admin/retrieval-quality`. It does not add new feedback statuses, storage fields, or backend endpoints.

## Data Flow

Existing flow remains:

`Q&A/Search feedback -> /search/feedback list -> Retrieval Quality detail -> PATCH /search/feedback/{id} -> preview/export promotion`

The new triage panel derives its state entirely from the selected feedback row already returned by the feedback list API:

- `outcome`
- `status`
- `selected_results`
- `expected`
- `operator_note`

The quick triage action reuses the existing review save path with `status="triaged"` and the current expected evidence editor contents.

## UI Behavior

The detail pane gains a "Triage next action" block above evidence editing:

- Dismissed rows: explain that the case is excluded from promotion.
- Rows with expected evidence: show ready-to-preview/export guidance.
- Helpful rows with selected evidence: show positive regression guidance.
- Not-helpful/missing/wrong-manual rows without expected evidence: explain what evidence to add next.
- Empty or selected-evidence-only rows: guide the operator to either use selected evidence or capture the expected source.

Quick actions are intentionally simple:

- `Use Selected Evidence` continues to copy the first selected result into the expected evidence editor.
- `Mark Triaged` saves current editor/note state with `triaged`.
- `Dismiss` continues to save current editor/note state with `dismissed`.

## Risk Controls

- No schema or API contract change.
- Existing promotion readiness logic remains the single source of truth in the page.
- Tests assert both static shell presence and browser-visible workflow text/buttons.
