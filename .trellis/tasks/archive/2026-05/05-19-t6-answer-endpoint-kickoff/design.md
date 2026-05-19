# T6 Phase 6 `/answer` endpoint — Design

## Scope

Ship a non-streaming, single-turn `/answer` endpoint that wraps `/retrieve` and
adds a fail-soft generation layer. Generation is default-off. Streaming,
multi-turn sessions, tool calling, answer cache, and LLM-as-judge are deferred.

## Module Layout

```text
src/tagmemorag/answer/
  __init__.py
  base.py
  generator.py
  openai_compatible.py
  prompt.py
```

- `base.py`: dataclasses and `AnswerGenerator` Protocol.
- `prompt.py`: role-separated prompt construction and citation validation.
- `generator.py`: provider factory and noop provider.
- `openai_compatible.py`: OpenAI-compatible chat completions client.
- `api.py`: `AnswerRequest`, `/answer` route, response assembly.
- `config.py`: `AnswerConfig`.

## API Contract

`AnswerRequest` extends `RetrieveRequest` with:

- `answer_token_budget: int | None = None`
- `include_retrieve: bool = True`

MVP response:

```json
{
  "schema_version": "answer.v1",
  "build_id": "...",
  "kb_name": "default",
  "trace_id": "...",
  "plan_id": "...",
  "answer": {
    "kind": "answer|refusal|error",
    "text": "...",
    "confidence": 0.0,
    "citations": [],
    "refusal_reason": "",
    "missing_evidence_hints": [],
    "model_id": "",
    "model_version": "",
    "prompt_version": "",
    "warnings": []
  },
  "retrieve": {},
  "warnings": []
}
```

HTTP status is 200 when retrieval succeeds, even for refusal or generation
failure. Existing auth scope is `search`.

## Config

`Settings.answer` defaults:

```yaml
answer:
  enabled: false
  provider: noop
  model_id: ""
  model_version: "v1"
  prompt_version: "answer_prompt.v1"
  base_url: "https://api.openai.com/v1"
  chat_completions_url: null
  api_key_env: "OPENAI_API_KEY"
  timeout_seconds: 30
  max_output_tokens: 512
  temperature: 0
```

Provider values: `noop | openai_compatible`.

## Data Flow

1. `/answer` receives `AnswerRequest`.
2. Route checks KB access and loads current state like `/retrieve`.
3. Route calls `_retrieve_impl` with the same request fields.
4. If retrieve `answerability.answerable=false`, return `answer.kind=refusal`.
5. If `Settings.answer.enabled=false`, return `answer.kind=error` with
   `refusal_reason="generation_disabled"`.
6. Build prompt from `context_pack.items` as untrusted data blocks.
7. Call configured `AnswerGenerator`.
8. Validate generated citation ids against retrieve citations.
9. Return answer plus retrieve payload and warnings.

## Prompt and Citation Guard

System/developer message contains only rules. Context appears only in user/data
message content with `context_item_id`, `citation_id`, source, and quoted
content. Prompt says source text is untrusted and cannot override instructions.

Output citations are filtered to known retrieve citation ids. Invalid citations
are dropped and surfaced in answer warnings.

## Failure Handling

- Retrieval errors preserve existing `/retrieve` behavior and may return
  existing structured API errors.
- Retrieval not answerable -> `answer.kind=refusal`.
- Generation disabled -> `answer.kind=error`, warning
  `answer_generation_disabled`.
- Provider config error / HTTP error / bad JSON -> `answer.kind=error`, retrieve
  payload preserved.

## Tests

- Config defaults and env/YAML override.
- Prompt builder keeps injected text in user/data content, not system rules.
- Citation guard drops unknown citations.
- `/answer` disabled returns `kind=error` plus retrieve payload.
- `/answer` refusal does not call generator.
- `/answer` noop happy path returns `kind=answer` with valid citations.
- Provider failure returns `kind=error` plus retrieve payload.
- Existing `/retrieve` API regression remains green.
