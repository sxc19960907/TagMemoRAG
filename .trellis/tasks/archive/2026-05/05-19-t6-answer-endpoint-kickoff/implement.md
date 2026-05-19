# T6 Phase 6 `/answer` endpoint — Implementation Checklist

## Pre-flight

- [x] Active task = `05-19-t6-answer-endpoint-kickoff`.
- [x] Read PRD/design and backend specs.
- [x] Run baseline focused retrieve test if needed.

## Slice 0 — Config + answer package contracts

- [x] Add `AnswerConfig` to `config.py`.
- [x] Add `src/tagmemorag/answer/base.py` dataclasses/protocol.
- [x] Add noop generator and factory.
- [x] Tests for config defaults and noop output.

## Slice 1 — Prompt builder + citation guard

- [x] Add `prompt.py` role-separated messages.
- [x] Add citation validation/filtering.
- [x] Tests for injection text staying in user/data content.
- [x] Tests for invalid citation warning/drop.

## Slice 2 — OpenAI-compatible provider

- [x] Add `openai_compatible.py` using httpx.
- [x] Env API key lookup by configured env name.
- [x] Parse JSON answer payload with text/citations.
- [x] Tests with `httpx.MockTransport`; no network.

## Slice 3 — `/answer` API

- [x] Add `AnswerRequest`.
- [x] Add `/answer` route with `search` scope.
- [x] Reuse `_retrieve_impl`.
- [x] Implement refusal, disabled, happy, provider-error response paths.
- [x] Tests for disabled/refusal/happy/failure/citations.

## Slice 4 — Docs/spec + validation

- [x] Update architecture B6 status/contract.
- [x] Run:

```bash
uv run pytest tests/unit/test_answer_config.py \
  tests/unit/test_answer_prompt.py \
  tests/unit/test_answer_generator.py \
  tests/unit/test_answer_api.py \
  tests/unit/test_api.py -q
git diff --check
```

## Rollback

Additive: remove answer package, config block, `/answer` route, tests, and spec
update. `/retrieve` remains unchanged.
