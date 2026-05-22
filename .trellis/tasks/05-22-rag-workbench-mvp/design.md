# RAG Workbench MVP — Design

## Architecture

Add a third lightweight admin page beside the existing operator pages:

- route: `/admin/rag-workbench`
- template: `src/tagmemorag/web/templates/rag_workbench.html`
- script: `src/tagmemorag/web/static/rag_workbench.js`
- styles: reuse `manual_library.css`, with small additive classes if needed

The page is server-rendered only for shell/config injection. All interactions
use existing JSON APIs.

## Data Flow

1. User enters KB, token, question, top_k, and source_k.
2. JS sends:

```json
{
  "kb_name": "default",
  "question": "...",
  "top_k": 5,
  "source_k": 8,
  "include_retrieve": true
}
```

to `POST /answer`.

3. JS renders:
   - `answer.kind`, `answer.text`, `answer.refusal_reason`;
   - `answer.citations`;
   - `retrieve.evidence`, `retrieve.results`, `retrieve.answerability`;
   - `warnings`, `plan_id`, `build_id`.

## UX Shape

Use a compact workbench layout rather than a marketing page:

- sticky topbar with KB, token, navigation links;
- left/main pane for question and answer;
- right pane for evidence and diagnostics;
- no nested cards; use the established pane/table styling.

## Error Handling

- HTTP errors render a status message with bounded text from response JSON.
- `answer.kind="error"` renders as an answer-state error but keeps retrieve
  evidence visible.
- Refusals render refusal reason and missing evidence hints.

## Compatibility

- Does not change `/answer`.
- Works with answer disabled, noop answer provider, and live providers.
- Auth token behavior matches current admin pages: user pastes a bearer token
  into a local password input.

## Tests

- Extend `test_manual_library_ui.py` or add a focused UI test file.
- Assert route serves expected shell elements and config.
- Assert static JS is served and contains `/answer` plus key render targets.
- Keep answer API tests unchanged.
