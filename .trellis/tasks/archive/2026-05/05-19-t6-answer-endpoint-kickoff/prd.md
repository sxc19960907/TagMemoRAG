# T6 Phase 6 answer endpoint kickoff

## Goal

Ship the Phase 6 `/answer` foundation: an optional endpoint that reuses
`/retrieve`, passes the resulting `context_pack` to a configured LLM, and
returns a structured answer with citations. `/retrieve` remains the primary
retrieval contract; `/answer` is a convenience layer for clients that want a
managed answer response instead of composing their own LLM call.

This task starts Phase 6 after T2 QueryPlan, T3 Reranker, and T5 replay have
landed. It must keep the generation layer thin, auditable, and fail-soft:
retrieval evidence should remain available even when answer generation is
disabled, refused, timed out, or fails.

## User Value

- API clients can ask one endpoint for an answer plus citations instead of
  manually calling `/retrieve` and a separate LLM.
- Operators get a controlled generation boundary with explicit config,
  prompt/model versioning, and failure behavior.
- Future answer-quality eval has a stable response contract to target.

## Confirmed Facts

- Architecture B6 says `/answer` should internally call `/retrieve`, reuse
  evidence/citation policy, and degrade to retrieval context on generation
  failure.
- Current code has `/search` and `/retrieve` only; no `/answer` endpoint, no
  LLM/chat adapter, and no `Settings.answer` or `Settings.llm` block.
- `/retrieve` already returns:
  - `results`
  - `evidence`
  - `citations`
  - `context_pack`
  - `answerability`
  - `plan_id`
  - `warnings`
- `retrieval.py:_answerability` already produces retrieval-side refusal hints:
  `answerable`, `confidence`, `warnings`, and `fallback_reason`.
- Existing external-call patterns:
  - embedding HTTP client uses OpenAI-compatible `/embeddings`, api-key env,
    timeout, and structured `EmbeddingError` / `InvalidConfigError`
  - reranker uses `httpx`, retry/fallback, circuit breaker, and never raises
    vendor failures into `/retrieve`
- Auth scopes currently use `search` for `/search` and `/retrieve`; `/answer`
  can probably reuse `search` unless a later policy introduces a separate
  generation scope.
- T5 replay is retrieval-only and does not evaluate generated answer text.

## Initial Direction

T6 should be implemented as a narrow, default-off generation layer:

- `/answer` request extends `RetrieveRequest` with answer-specific controls.
- `/answer` calls the existing retrieval implementation or a shared retrieval
  helper so evidence/citations/context stay identical to `/retrieve`.
- If retrieval says not answerable, `/answer` returns a structured refusal
  without calling the LLM by default.
- If LLM generation fails or is disabled, `/answer` returns retrieval payload
  plus a fail-soft answer object.
- LLM provider should be OpenAI-compatible HTTP first, with a deterministic
  fake/noop provider for tests and offline dev.
- Streaming and multi-turn sessions are not in the first implementation slice
  unless explicitly chosen.

## Requirements

- Define `/answer` request/response contract.
- Define refusal shape for insufficient evidence.
- Add config for answer generation that defaults off.
- Add LLM adapter boundary with no network in tests.
- Treat retrieved content as data, not instructions, in prompt construction.
- Preserve `/retrieve` behavior and response shape.
- Surface citations in the answer response without inventing a second citation
  system.
- Fail soft on generation errors: return retrieval context and warnings.
- Add focused tests for disabled, refusal, happy path, vendor failure, and
  citation preservation.

## Out of Scope Candidates

- Stateful multi-turn sessions.
- Streaming responses.
- Tool calling.
- LLM-as-judge faithfulness gate.
- Answer cache.
- Selecting a specific production vendor/model as a hard-coded dependency.
- Changing `/retrieve` output semantics.

## Decisions

### D1 MVP Scope: non-streaming single-turn `/answer`

The first T6 implementation includes only non-streaming, single-turn `/answer`
with default-off OpenAI-compatible generation. Streaming, multi-turn sessions,
tool calling, and answer caching are deferred.

Reasoning: this gives clients the main answer + citation capability while
keeping the response contract reviewable. It avoids entangling generation
correctness, stream transport, and conversation state before the basic answer
contract has been validated.

Trade-off: chat clients will not get token streaming or server-side session
memory in the first slice; they can still use `/retrieve` or client-managed
history until those follow-up tasks land.

### D2 Refusal Contract: structured answer object, HTTP 200

When retrieval says the question is not answerable or there is insufficient
context, `/answer` returns HTTP 200 with `answer.kind="refusal"` and preserves
the full retrieve payload.

```json
{
  "answer": {
    "kind": "refusal",
    "text": "",
    "confidence": 0.0,
    "refusal_reason": "no_results",
    "missing_evidence_hints": [],
    "citations": []
  },
  "retrieve": { "...": "full retrieve payload" },
  "warnings": ["answer_refused:no_results"]
}
```

Reasoning: clients can handle success, refusal, and generation failure through
one response schema while still receiving the retrieval context for debugging or
fallback UI.

Trade-off: using non-200 responses or `answer: null` is simpler on paper, but
it makes "retrieval succeeded, answer refused" look like transport/API failure
and forces clients to special-case missing answer fields.

The answer object has these MVP kinds:

- `answer`: generated answer text exists.
- `refusal`: retrieval completed but evidence/context was insufficient.
- `error`: retrieval completed but generation failed or was disabled; retrieval
  context is still returned.

### D3 Faithfulness Eval MVP: deterministic contract gate

T6 first slice uses deterministic contract tests plus citation coverage checks,
not LLM-as-judge. The gate verifies:

- generated answers only cite citation ids present in the retrieve payload
- prompt construction includes context items as quoted/data sections, not as
  system/developer instructions
- refusal happens when `retrieve.answerability.answerable=false`
- generation failure returns `answer.kind="error"` plus retrieve context
- no API keys or raw document text are logged

Reasoning: T6 needs a regression gate, but LLM-as-judge would add vendor
coupling and noisy nondeterminism before the basic `/answer` contract exists.

Trade-off: this does not prove semantic faithfulness. It only proves the answer
layer respects citations and refusal mechanics. Deeper faithfulness scoring can
be a follow-up once real answer traces exist.

### D4 LLM Adapter / Provider Scope: protocol + noop + OpenAI-compatible HTTP

T6 ships a vendor-neutral `AnswerGenerator` protocol with two concrete
implementations:

- `NoopAnswerGenerator` / fake deterministic provider for default-off behavior
  and tests.
- OpenAI-compatible HTTP chat-completions provider behind config, with no
  vendor-specific model hard-coded.

Config should live under `Settings.answer` and default to:

```yaml
answer:
  enabled: false
  provider: noop
```

Reasoning: `/answer` must be deployable and testable without network,
credentials, or model selection, while still giving operators an obvious path to
enable a real provider.

Trade-off: implementing only noop/fake would avoid external API surface now but
would not actually deliver managed answers. Hard-coding one vendor would be
faster but would violate the vendor-specifics discipline already used for
reranker and embeddings.

### D5 Prompt-Injection Defense: role separation + structured context data

T6 uses strict role separation plus structured context serialization:

- System/developer prompt contains the answer rules and citation requirements.
- Retrieved `context_pack.items` are serialized as quoted data blocks with
  stable `context_item_id` and `citation_id`.
- The prompt explicitly states that retrieved content is untrusted source data
  and must not override instructions.
- The generator validates output citations against retrieve citations and drops
  or flags invalid citations.
- Tests include a retrieved chunk that says "ignore previous instructions" and
  verify it is passed only as data, not as an instruction message.

Reasoning: `/answer` introduces an LLM boundary where retrieved manual text can
contain adversarial instructions. The defense must be visible in code and
testable without relying on model behavior.

Trade-off: this does not fully solve prompt injection at model-behavior level,
but it prevents the most dangerous implementation mistake: mixing retrieved
content into the system/developer role or trusting model-emitted citations.

## Open Questions

- None blocking after D1-D5. Detail-level design choices are captured in
  `design.md`.

## Acceptance Criteria

- [x] MVP scope decision recorded.
- [x] Refusal response shape decided and documented.
- [x] Faithfulness eval stance for MVP decided and documented.
- [x] Prompt-injection defense recorded and tested.
- [x] `prd.md`, `design.md`, and `implement.md` exist before implementation.
- [x] Eval slice: focused `/answer` unit/API tests plus existing `/retrieve`
      API regression.
- [x] Implementation preserves existing `/retrieve` tests.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
