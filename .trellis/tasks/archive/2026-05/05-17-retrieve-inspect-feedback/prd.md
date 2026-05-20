# Phase 3.5: Retrieve Inspect and Feedback

## Goal

Add lightweight production diagnostics around `/retrieve` and extend retrieval feedback so Agent-facing context quality can be reviewed and turned into eval data later.

This task should make `/retrieve` explainable without changing ranking behavior. It should not implement visual evidence, parent context expansion, `/answer`, OCR, assets, or learned fusion.

## Requirements

- Add safe inspect/debug metadata for `/retrieve` when `debug=true`.
- Inspect metadata should explain:
  - retrieval strategy;
  - candidate/index participation summary;
  - evidence count;
  - citation count;
  - context item count;
  - token budget and estimate;
  - answerability/fallback reason;
  - selected evidence/context IDs and stable chunk/doc IDs.
- Extend feedback records to support retrieve-specific fields:
  - `retrieve_id`;
  - selected evidence ids;
  - selected context item ids;
  - answerable/no-answer flag;
  - failure/fallback reason.
- Add `/retrieve/feedback` as an alias for retrieve feedback submission while keeping existing `/search/feedback` compatible.
- Do not store raw context pack content, raw retrieved text, query tokens, vectors, or unsafe paths beyond existing bounded query/expected fields.

## Acceptance Criteria

- [ ] `/retrieve` debug response includes a safe `retrieve_inspect` block.
- [ ] Debug block does not include raw vectors, raw query tokens, or full hidden candidate lists.
- [ ] Feedback submission accepts retrieve-specific fields and persists them.
- [ ] Existing search feedback tests remain compatible.
- [ ] Tests cover retrieve debug, retrieve feedback, and auth scope.
- [ ] Full tests and eval CI pass.

## Out of Scope

- Admin UI for inspect output.
- Visual evidence or asset diagnostics.
- `/answer` feedback.
- Automatic eval promotion from context packs.
- Ranking/fusion changes.
