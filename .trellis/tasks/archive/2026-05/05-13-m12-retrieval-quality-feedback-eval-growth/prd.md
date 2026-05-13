# M12 Retrieval Quality Feedback Loop and Eval Dataset Growth

## Goal

Close the loop between real retrieval behavior and regression testing. M12 adds a lightweight, file-backed feedback capture path for search results, an operator review workflow, and tools to promote useful feedback into eval JSONL cases. The outcome is a growing eval suite that reflects real user failures and lets future search, metadata, tag, and rebuild changes prove they improve quality instead of merely changing scores.

## Background / Known Context

- M0 introduced WAVE-RAG search, anchors, `GraphState`, FastAPI, CLI, and zero-downtime rebuild.
- M3 introduced `tagmemorag eval run`, JSONL eval suites, matcher-based expected results, metrics (`precision_at_k`, `recall_at_k`, `mrr`, `hit_at_k`), per-case thresholds, and isolated eval storage.
- M4 added trace IDs, metrics, and safe observability constraints.
- M5-M11 added manual metadata, filters/facets, tag-aware search boosts, managed manual library operations, admin UI, bulk import, deterministic tag suggestions, Qdrant vector backend, and tag governance.
- Current eval fixture coverage is intentionally small: `tests/fixtures/eval/coffee.jsonl` has three coffee-machine cases. It is useful as a smoke regression gate but too narrow to guide future retrieval tuning.
- `/search` already returns `trace_id`, `build_id`, `search_time_ms`, result metadata, and full top-k result bodies.
- Auth scopes already distinguish read/search from rebuild/admin operations. Feedback capture should not require write/rebuild privileges if the deployment wants end-user feedback.
- Existing storage conventions are file-backed JSON/JSONL with atomic writes where persistence matters. No database is in scope yet.

## Assumptions

- Feedback records are stored per KB under a file-backed location, recommended: `{storage.data_dir}/{kb_name}/feedback/search-feedback.jsonl` or a configurable feedback root.
- Feedback capture should persist bounded metadata about a search interaction, not raw full manuals or unbounded result text.
- The search response can include a stable `search_id` derived from trace/build/request context, or feedback can accept `trace_id` plus explicit result references.
- Operators, not end users, decide whether feedback becomes an eval case.
- M12 can add admin UI controls to the existing `/admin/manual-library` shell or create a small `/admin/retrieval-quality` shell. Recommended MVP: reuse the existing admin shell only if it stays readable; otherwise add a separate page.
- The feedback loop is advisory. It does not automatically retrain, tune ranking parameters, or mutate anchors/tags.

## Requirements

### 1. Search Feedback Capture

- Add a feedback data model for search interactions with:
  - `feedback_id`
  - `kb_name`
  - `trace_id` / `search_id`
  - `build_id`
  - query text or a bounded query summary
  - timestamp
  - rating or outcome (`helpful`, `not_helpful`, `missing_result`, `wrong_manual`, `other`)
  - optional selected result identifiers (`node_id`, `anchor_key`, `source_file`, `header`, `manual_id`)
  - optional expected result hints (`source_file`, `header`, `text_contains`, `manual_id`, tags)
  - optional operator/user note, bounded length
  - review status (`new`, `triaged`, `promoted`, `dismissed`)
- Feedback writes must be append-safe and constrained to the configured feedback/KB root.
- The API must validate payload size and reject unsafe or malformed fields with structured errors.
- Do not store API keys, raw embedding vectors, full document chunks, or unbounded result text.

### 2. Search Response Linkage

- Extend `/search` responses with enough information to submit feedback without clients reverse-engineering internals.
- Preserve backward compatibility for existing clients.
- Cache hits must still produce valid feedback linkage for the current request trace.
- Feedback capture must work for filtered searches, synonym-resolved tag filters, and cached responses.

### 3. Feedback Listing and Review

- Provide APIs to list feedback by `kb_name`, status, outcome, date range or limit.
- Provide review actions:
  - update status
  - add operator note
  - dismiss
  - mark as candidate for eval promotion
- Listing responses must be bounded and safe for UI display.
- Require KB allowlist access for all feedback operations.
- Recommended auth:
  - create feedback: `search` scope
  - list/review/promote: `admin` or a future `quality.write` scope; MVP may use `admin`.

### 4. Promote Feedback to Eval Drafts

- Add a non-mutating preview that converts selected feedback into eval case candidates.
- Add a commit/export operation that writes JSONL eval draft files, recommended path: `eval_drafts/{kb_name}/feedback-{date}.jsonl` or a configured output path.
- Eval draft cases must follow the existing `EvalCase` schema:
  - `id`
  - `query`
  - `kb_name`
  - `relevant`
  - `tags`
  - `notes`
  - optional per-case thresholds
- Promotion must avoid duplicate case IDs and should produce deterministic IDs.
- Promotion must never overwrite an existing eval suite without explicit overwrite/append behavior.
- Drafts should prefer precise matchers from feedback/result references: `source_file`, `header`, `anchor_key`, `metadata.manual_id`, `text_contains` when supplied.

### 5. Eval Dataset Growth

- Expand the checked-in eval fixture coverage beyond the current three coffee cases.
- Add cases that cover:
  - metadata filters and manual IDs
  - tag/canonical/synonym retrieval behavior
  - common failure-code / troubleshooting queries
  - at least one negative or hard case where multiple manuals or sections are plausible
- Keep tests deterministic with `HashingEmbedder`; do not require external model downloads.
- Ensure fixture cases are not brittle to harmless ranking ties where possible.

### 6. CLI Helpers

- Add thin CLI helpers over the same backend/service behavior:
  - record or import feedback from JSON
  - list feedback
  - preview eval case promotion
  - export/promote feedback to JSONL
  - run eval against promoted drafts
- CLI output should be JSON for automation-friendly workflows.

### 7. Admin UI

- Add an operator-facing view for retrieval quality:
  - feedback table with filters by status/outcome/KB/query text
  - detail panel showing query, selected result references, notes, and current review status
  - controls to dismiss, triage, or mark for eval promotion
  - promotion preview showing generated eval JSONL rows
  - explicit export/commit controls
- Keep UI dense and operational, consistent with `/admin/manual-library`.

### 8. Observability and Safety

- Log only low-cardinality safe fields: `kb_name`, operation, status/outcome, counts, and trace id.
- Do not create metrics labels from raw query text, feedback notes, result text, manual titles, or tags.
- Feedback storage errors should return structured `{code, message, detail}` responses.
- Feedback failures must not break `/search`; feedback creation is a separate API path.

## Acceptance Criteria

- [ ] Clients can submit bounded feedback for a search result using the returned search/trace context.
- [ ] Feedback is stored per KB in a file-backed, path-safe, append-safe format.
- [ ] Operators can list and review feedback with status/outcome filters.
- [ ] Operators can preview promotion of feedback into existing eval JSONL case shape.
- [ ] Operators can export or commit promoted feedback to a deterministic eval draft JSONL file without accidental overwrite.
- [ ] CLI helpers cover list/preview/export workflows using the same service code as API/UI.
- [ ] Admin UI exposes feedback review and eval promotion controls.
- [ ] Eval fixtures are expanded and `tagmemorag eval run` continues to pass deterministically with `HashingEmbedder`.
- [ ] Auth and KB allowlist checks are enforced for create/list/review/promote operations.
- [ ] Existing `/search`, cache, metrics, tracing, eval runner, manual library, and tag governance behavior remain backward compatible.
- [ ] Tests cover feedback model validation, storage append/list/review, API auth, search linkage, eval promotion, CLI helpers, UI static/route behavior, and expanded eval cases.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Unit/API/CLI/UI tests cover the feedback loop and eval promotion workflow.
- Eval fixtures are expanded with deterministic regression coverage.
- Documentation explains how to collect feedback, review it, promote it, and run eval gates.
- `uv run pytest tests/ -q` passes.
- Any durable backend conventions learned during implementation are added to `.trellis/spec/backend/`.

## Out of Scope

- Learning-to-rank, online ranking updates, automatic parameter tuning, or reinforcement learning.
- LLM-generated relevance judgments.
- Database-backed feedback store.
- Multi-user approval workflow.
- PII redaction pipeline beyond bounded safe-field validation.
- Automatic anchor/tag/manual metadata mutation from feedback.
- Production analytics dashboards beyond a basic operational review UI.

## Follow-Up Ideas

- Saved eval suites with approval/release state.
- CSV export and BI-friendly feedback summaries.
- Search quality trend charts by KB/build_id.
- Automatic duplicate feedback clustering.
- LLM-assisted eval case draft cleanup reviewed by an operator.
- Dedicated `quality.read` / `quality.write` auth scopes.
