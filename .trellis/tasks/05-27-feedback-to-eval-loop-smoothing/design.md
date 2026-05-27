# Feedback To Eval Loop Smoothing Design

## Scope

This task improves browser handoff and selection state. It does not change feedback storage, eval promotion schemas, or eval runner behavior.

## Flow

1. User clicks `Not helpful` in Q&A.
2. Q&A posts feedback as it does today.
3. On success, Q&A stores `feedback_id` on the active turn.
4. Feedback note renders a link:
   `/admin/retrieval-quality?kb_name=<kb>&feedback_id=<feedback_id>`.
5. Retrieval Quality reads `feedback_id` from the URL.
6. After loading feedback rows, it selects the matching row and renders detail.

## Compatibility

If a feedback id is not found in the loaded rows, Retrieval Quality keeps the normal table view and status message. The URL parameter is a convenience, not a required backend query.

## Rollback

Revert QA JS, Retrieval Quality JS, and tests. No data migration is required.
