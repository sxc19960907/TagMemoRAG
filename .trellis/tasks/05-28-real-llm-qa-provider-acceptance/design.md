# Real LLM QA Provider Acceptance Design

## Scope

This task adds an acceptance layer around the existing `openai_compatible` answer provider. It does not introduce a new provider contract; it verifies that the current contract is safe enough for user-facing `/qa` usage when an external model is enabled.

## Architecture

The existing request flow remains:

```text
/qa browser -> /answer API -> /retrieve -> build_answer_prompt -> AnswerGenerator -> validate_generation_citations -> QA UI render
```

The task tightens the post-generation contract:

- The prompt already requires citation ids after evidence-backed claims.
- `_parse_chat_completion` already extracts citation ids from provider metadata and bracketed text.
- `validate_generation_citations` already drops invalid citation ids.
- The missing guard is that a model can return fluent text with no valid citations while the API still marks `answer.kind=answer`.

The implementation should make citation validation explicit: if the provider returns text but no valid citation ids while the prompt has allowed citation ids, convert the response into an answer-generation failure/warning path instead of a successful grounded answer. The API can then return `answer.kind=error` with existing `answer_generation_failed:*` warning semantics.

## Browser Acceptance

Add a dedicated opt-in browser integration test that:

- Starts the local server with a temp config using `answer.provider=openai_compatible`.
- Reads the API key only from the configured environment variable, defaulting to `DEEPSEEK_API_KEY` unless overridden by test env.
- Uses real product manuals already in `product_manuals/`.
- Opens `/admin/manual-library`, uploads/indexes the manuals, then opens `/qa?kb_name=default`.
- Asks an answerable question and verifies:
  - status reaches "Answer ready."
  - answer text is non-empty
  - citation chips render
  - source cards render the expected manual
  - no unsafe internal identifiers leak
- Asks an unsupported/insufficient-evidence question and verifies the page does not show a fabricated confident replacement/part answer.

The real-model test must be skipped by default unless all required gates are present:

- `TAGMEMORAG_RUN_BROWSER_UI=1`
- `TAGMEMORAG_RUN_REAL_LLM_QA=1`
- configured answer API key env var is present
- real manual PDFs are available

## Compatibility

- `noop` provider behavior must remain unchanged.
- Existing answer failure payload semantics should be reused.
- No secrets are logged or embedded in committed config.
- Browser acceptance may use hashing embeddings to keep the test focused on real answer generation, not external embedding availability.

## Rollback

If real LLM acceptance is flaky, the opt-in test can remain skipped by default. The citation-gating unit behavior should stay because it protects the user-facing answer contract independent of external services.
