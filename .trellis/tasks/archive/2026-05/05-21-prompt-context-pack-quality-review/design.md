# Prompt and Context Pack Quality Review — Design

## Scope

Improve answer prompt/context quality with bounded prompt changes and
diagnostic fixtures. This task should make citation/refusal/conflicting
evidence expectations explicit without changing retrieval ranking or public
answer response shape.

## Goals

- Add diagnostics cases for citation misses and conflicting evidence.
- Strengthen the answer system prompt around:
  - citing every evidence-backed claim;
  - not citing evidence that does not support the claim;
  - stating uncertainty when context conflicts;
  - refusing when context is insufficient.
- Preserve citation validation and safe answer failure behavior.
- Keep changes reversible and covered by tests.

## Non-Goals

- Do not tune ranking, reranking, or context-pack ordering in this task unless
  tests prove a bounded issue.
- Do not introduce live DeepSeek verification unless env/cost gates are already
  present and cheap.
- Do not change `/answer` response schema.
- Do not make agentic mode default-on.

## Proposed Shape

### Prompt Contract

Update `SYSTEM_PROMPT` in `src/tagmemorag/answer/prompt.py` with explicit but
compact instructions:

- every evidence-backed claim needs exact citation ids;
- citation ids must support the claim they follow;
- conflicting evidence should be acknowledged instead of averaged away;
- insufficient context should produce an insufficient-evidence statement.

Keep retrieved context in the user message as untrusted data.

### Diagnostics Fixtures

Extend `tests/fixtures/answer_quality/basic.jsonl` with cases for:

- citation miss: answer makes a supported claim but has no citation;
- conflicting evidence: answer should acknowledge conflict rather than choose
  an unsupported single truth.

The deterministic C2 diagnostics can represent these as expected labels:
`citation_supported=false` for missing citations, and `grounded=false` when the
answer claims a fact contradicted by authored context markers.

### Tests

- Prompt tests assert new instructions are present and retrieved content stays
  outside the system message.
- Answer-quality tests assert the new fixture cases run and remain bounded.
- Answer API tests stay green.

## Compatibility

- No schema changes.
- No dependency changes.
- Runtime behavior changes only through prompt wording when generation is
  enabled.
- Rollback is reverting prompt text and fixture/test additions.

## Validation Gates

- `tests/unit/test_answer_prompt.py`
- `tests/unit/test_answer_quality_eval.py`
- `tests/unit/test_answer_api.py`
- `tests/unit/test_answer_generator.py`
- C2 answer-quality command
