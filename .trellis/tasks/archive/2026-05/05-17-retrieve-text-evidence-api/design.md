# Design — Retrieve Text Evidence API

## Approach

Reuse existing search execution. `/retrieve` should not introduce a new ranking path in Phase 3 MVP.

Data flow:

```text
RetrieveRequest
  -> embed query
  -> existing metadata narrowing + execute_search()
  -> retrieval.build_retrieve_response()
       -> raw results
       -> text evidence
       -> citations
       -> context_pack
       -> answerability
```

## Module Placement

- `api.py`: route, auth, request validation, embedding/search orchestration.
- `retrieval.py`: pure response assembly from search results.

This keeps evidence/context formatting testable without FastAPI.

## Response Contract

Evidence is request-scoped but points to durable IDs:

- `evidence_id`: request scoped.
- `citation_id`: request scoped.
- `chunk_id`: persistent when present.
- `doc_id`: persistent when present.
- `node_id`: compatibility/debug only.

Context pack items are selected from evidence until the budget is exhausted.

## Answerability

MVP rules:

- no results -> `answerable=false`, confidence `0.0`, warning `no_results`;
- results present -> `answerable=true`, confidence based on top score clamped to `[0, 1]`;
- if no context items fit budget -> `answerable=false`, warning `context_budget_exhausted`.

## Compatibility

- `/search` unchanged.
- `/retrieve` debug is additive and safe.
- No raw vectors, raw query tokens, or unsafe file paths in debug.
