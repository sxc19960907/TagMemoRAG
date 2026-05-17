# Design — Retrieve Inspect and Feedback

## Retrieve Inspect

Add a safe `debug.retrieve_inspect` block to `/retrieve` responses when debug is enabled.

Shape:

```json
{
  "schema_version": "retrieve_inspect.v1",
  "retrieve_id": "...",
  "result_count": 3,
  "evidence_count": 3,
  "citation_count": 3,
  "context_item_count": 2,
  "token_budget": 4000,
  "token_count_estimate": 540,
  "answerable": true,
  "fallback_reason": "",
  "selected": [
    {
      "rank": 1,
      "evidence_id": "ev_001",
      "citation_id": "cit_001",
      "context_item_id": "ctx_001",
      "doc_id": "manual-a",
      "chunk_id": "chunk:...",
      "score": 0.91
    }
  ]
}
```

Rules:

- No raw text beyond regular evidence/context response.
- No raw query tokens.
- No vectors.
- Keep selected list bounded by returned evidence.

## Feedback Extension

Existing `SearchFeedback` remains the storage format but gets additive fields:

- `retrieve_id: str`
- `selected_evidence_ids: tuple[str, ...]`
- `selected_context_item_ids: tuple[str, ...]`
- `answerable: bool | None`
- `failure_reason: str`

`/retrieve/feedback` calls the same creation path as `/search/feedback`; this keeps review/list/promote workflow compatible.

## Compatibility

- Existing feedback rows without new fields load with empty/default values.
- Existing `/search/feedback` request shape remains valid.
- `/retrieve` debug only appears when `debug=true` or config debug is enabled.
