# Design: RAG feedback eval closure

## Scope

This record documents the completed inline implementation that connected browser Q&A feedback to Retrieval Quality and eval draft export.

## Data Flow

```text
Q&A page feedback
  -> POST /search/feedback
  -> retrieval_feedback search-feedback.jsonl
  -> GET /search/feedback
  -> Retrieval Quality review workspace
  -> PATCH /search/feedback/{feedback_id}
  -> search-feedback-reviews.json overlay
  -> POST /search/feedback/promote/preview
  -> POST /search/feedback/promote
  -> eval_drafts/<kb>/feedback-<date>.jsonl
  -> tagmemorag.eval.dataset.load_eval_suite
```

## Persistence Contract

- Raw feedback remains append-only JSONL.
- Review updates, including expected evidence edits, live in the existing review overlay.
- Promotion export writes JSONL eval cases compatible with the existing eval loader.
- No parallel feedback store was introduced.

## UI Contract

- Q&A feedback is optimistic in the page but shows whether backend persistence succeeded.
- Retrieval Quality derives source labels from feedback shape and notes.
- Promotion readiness is rendered from backend preview/export response, not independently invented in the UI.
- The raw JSON preview remains visible for debugging.

## Compatibility

- Legacy feedback rows without `plan_id` or expected overlay continue to parse.
- Rows without selected/expected evidence show empty states and remain reviewable.
- Export retains duplicate protection unless append/overwrite is explicitly selected.
