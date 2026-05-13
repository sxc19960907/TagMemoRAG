# design.md - M12 Retrieval Quality Feedback Loop and Eval Dataset Growth

## Scope

M12 adds a file-backed retrieval-quality workflow around the existing search and eval systems. The core should live in backend service modules and be reused by API, CLI, and admin UI. It should not change WAVE-RAG ranking behavior directly; it creates the data and tooling needed to evaluate ranking changes safely later.

## Current State

```text
/search
  -> embeds query
  -> wave_search()
  -> returns trace_id, build_id, top-k Result objects

tagmemorag eval run
  -> load JSONL EvalCase suite
  -> build/load KB
  -> wave_search()
  -> match ExpectedResult objects
  -> report precision/recall/MRR/hit
```

Important existing files:

- `src/tagmemorag/api.py`: `/search`, trace/cache behavior, auth dependencies, admin route mounting.
- `src/tagmemorag/types.py`: `Result` and `GraphState` contracts.
- `src/tagmemorag/eval/dataset.py`: JSONL eval schema and validation.
- `src/tagmemorag/eval/runner.py`: eval execution against built or isolated KBs.
- `src/tagmemorag/eval/matching.py`: matcher semantics for expected results.
- `src/tagmemorag/eval/report.py`: report serialization.
- `src/tagmemorag/cli.py`: `eval run` and other CLI command patterns.
- `src/tagmemorag/storage/atomic.py`: atomic file write helper.
- `src/tagmemorag/auth/`: scope and KB allowlist enforcement.
- `src/tagmemorag/web/templates/manual_library.html` and static assets: existing dense admin UI style.

## Proposed Module Boundary

Add `src/tagmemorag/retrieval_feedback.py`.

Responsibilities:

- Define feedback dataclasses and serialization.
- Validate feedback payloads and bound free-text fields.
- Resolve per-KB feedback storage paths under a safe root.
- Append feedback JSONL records.
- List/filter feedback records.
- Update review status/operator note.
- Build eval case promotion previews from feedback records.
- Export promoted eval draft JSONL with deterministic IDs and overwrite/append controls.

Keep this module independent of FastAPI request objects, CLI argparse, and browser state.

## File Contracts

Recommended default feedback path:

```text
{storage.data_dir}/{kb_name}/feedback/search-feedback.jsonl
```

Recommended review-state path:

```text
{storage.data_dir}/{kb_name}/feedback/search-feedback-reviews.json
```

Rationale:

- JSONL append works well for immutable feedback events.
- A small JSON review overlay avoids rewriting the entire append log for status changes.
- Both stay under the KB storage root and match existing file-backed conventions.

Recommended eval draft path:

```text
eval_drafts/{kb_name}/feedback-YYYYMMDD.jsonl
```

The implementation may make draft root configurable later; MVP can use a conservative default and explicit CLI/API output path.

## Data Contracts

### SearchFeedback

```python
@dataclass(frozen=True)
class SearchFeedback:
    feedback_id: str
    kb_name: str
    trace_id: str
    search_id: str
    build_id: str
    query: str
    outcome: Literal["helpful", "not_helpful", "missing_result", "wrong_manual", "other"]
    created_at: str
    selected_results: tuple[FeedbackResultRef, ...] = ()
    expected: tuple[FeedbackExpectedRef, ...] = ()
    note: str = ""
    status: Literal["new", "triaged", "promoted", "dismissed"] = "new"
    operator_note: str = ""
```

### FeedbackResultRef

```python
@dataclass(frozen=True)
class FeedbackResultRef:
    rank: int | None = None
    node_id: int | None = None
    anchor_key: str = ""
    source_file: str = ""
    header: str = ""
    manual_id: str = ""
```

### FeedbackExpectedRef

Use fields compatible with `ExpectedResult`:

```python
@dataclass(frozen=True)
class FeedbackExpectedRef:
    source_file: str = ""
    header: str = ""
    anchor_key: str = ""
    text_contains: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

### EvalPromotionPreview

```python
@dataclass(frozen=True)
class EvalPromotionPreview:
    kb_name: str
    feedback_ids: tuple[str, ...]
    cases: tuple[dict[str, Any], ...]
    skipped: tuple[dict[str, Any], ...]
    output_path: str
```

## Search Linkage

Add a `search_id` to `/search` responses. It should be stable enough for the response but not sensitive:

```text
sha256(kb_name + build_id + trace_id + normalized question + canonical filters + top_k)
```

The current cache key already canonicalizes request params and filters. M12 can either reuse the same canonicalization helper or add a narrower `_compute_search_id()`.

Important cache behavior:

- Cache hit payloads are stored without `trace_id`, `search_time_ms`, and `cache`.
- M12 must also avoid storing stale `search_id` in cached payloads, or recompute it on every response.
- Feedback should accept explicit query/build/result refs even if clients cannot provide `search_id`, but `search_id` improves traceability.

## API Design

Recommended endpoints:

```text
POST /search/feedback
GET  /search/feedback?kb_name=...&status=...&outcome=...&limit=...
PATCH /search/feedback/{feedback_id}
POST /search/feedback/promote/preview
POST /search/feedback/promote
```

Auth:

- `POST /search/feedback`: `search` scope, KB allowlist.
- `GET/PATCH/promote`: `admin` scope for MVP, KB allowlist.

Error handling:

- Invalid payload/path/status/outcome -> `INVALID_INPUT`.
- Unknown feedback id -> `INVALID_REQUEST`.
- Forbidden KB/scope -> existing auth errors.

## CLI Design

Add a `feedback` command group:

```bash
python -m tagmemorag feedback submit --kb default --json feedback.json
python -m tagmemorag feedback list --kb default --status new --limit 50
python -m tagmemorag feedback review --kb default --feedback-id ... --status triaged --operator-note "..."
python -m tagmemorag feedback promote-preview --kb default --feedback-id ... --output eval_drafts/default/feedback.jsonl
python -m tagmemorag feedback promote --kb default --feedback-id ... --output eval_drafts/default/feedback.jsonl --append
```

All CLI outputs should be JSON to support scripting.

## Admin UI Design

Option A: add a new `/admin/retrieval-quality` route.

Pros:

- Keeps manual library UI from becoming too crowded.
- Allows feedback-specific filters and promotion preview without nesting more tables in one dialog.

Cons:

- Adds another template/static entry point.

Recommended MVP: new `/admin/retrieval-quality`, reusing the same CSS patterns and token handling.

Required UI regions:

- Top controls: KB, API token, refresh.
- Feedback table: created time, outcome, status, query, build_id, selected refs.
- Detail pane: feedback details, notes, expected refs, review controls.
- Promotion pane: preview JSONL rows and export/commit button.

## Eval Promotion Rules

For each feedback record:

1. Use `query` and `kb_name` directly.
2. Build deterministic `id`, e.g. `feedback-{feedback_id}` or `feedback-{kb}-{short-hash}`.
3. Build `relevant` from `expected` refs if present.
4. If no expected refs exist, use selected result refs only for positive/helpful feedback; skip negative feedback without an expected target.
5. Add tags such as `feedback`, outcome, and any supplied domain tags.
6. Add notes summarizing source feedback id, outcome, and operator note.

Skip with reasons when:

- query is missing/too short after validation.
- no usable `relevant` matcher can be produced.
- case id duplicates an existing output file and append mode disallows duplicates.

## Storage and Safety

- Use `Path.resolve().relative_to(root.resolve())` checks for feedback and draft paths.
- Use atomic writes for review overlays and eval draft exports.
- For JSONL append, open in append mode after ensuring parent directory exists under root. Include newline-delimited complete JSON objects only.
- Bound text fields:
  - query: max 1000 characters
  - note/operator note: max 2000 characters
  - text_contains items: max 200 characters each, max 8 items
  - selected/expected refs: max 20 each
- Listing default limit should be small, e.g. 50, max 500.

## Compatibility

- Existing `/search` clients continue to work; added fields are additive.
- Existing eval JSONL schema remains valid.
- Existing eval reports remain valid; promotion writes new suites/drafts rather than mutating runner behavior.
- Deployments without feedback files return empty feedback lists.

## Rollout / Rollback

- Rollout can happen in layers:
  1. Backend service + API.
  2. CLI helpers.
  3. Admin UI.
  4. Expanded eval fixtures and docs.
- Removing feedback files disables the review history without affecting search or eval.
- If UI is delayed, API/CLI can still deliver the feedback loop MVP.
