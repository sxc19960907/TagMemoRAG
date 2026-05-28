# Real LLM QA provider acceptance

## Goal

Validate that the user-facing `/qa` browser experience works with a real OpenAI-compatible answer provider, real manuals, and real citations instead of relying only on the deterministic `noop` provider.

This task closes the next delivery gap between "offline/demo QA works" and "a user can try the RAG system with an actual model and inspect grounded answers."

## Confirmed Facts

- `/answer` already supports `answer.provider=openai_compatible`.
- API keys are configured by environment variable name (`answer.api_key_env`) and must not be written into YAML, logs, test output, reports, or committed files.
- Existing browser integration tests exercise `/qa` with real PDFs, DOCX, OCR, source previews, citations, and insufficient-evidence refusal, but they use the deterministic `noop` provider.
- `production-provider smoke` validates provider configuration through CLI/TestClient, but does not cover the real browser page a user sees.
- Tests that require browser or external services are opt-in and skipped clearly by default.

## Requirements

- Add an opt-in browser acceptance path for a real `openai_compatible` answer provider on `/qa`.
- Use real manuals already present in the project, not fabricated-only fixtures, for the acceptance flow.
- Keep the default test suite offline and deterministic. Real model acceptance must skip clearly when the required environment variable is absent.
- Verify that the visible QA page shows a successful answer with source cards and citation chips for answerable questions.
- Verify that unsupported questions do not become confident fabricated answers.
- Ensure real model answers are not accepted as successful when they omit valid citation ids.
- Keep secrets safe: no raw API keys in YAML, reports, console assertions, browser output, or committed artifacts.
- Preserve existing `/answer` and `/qa` behavior for the `noop` provider.

## Acceptance Criteria

- [ ] A Trellis design and implementation plan exist for the real LLM browser acceptance work.
- [ ] The `openai_compatible` answer generator path or answer validation rejects/flags uncited model answers so browser acceptance cannot pass on citation-free text.
- [ ] An opt-in browser integration test can run `/qa` against a real OpenAI-compatible answer provider and real product manuals when the configured env var is present.
- [ ] The same opt-in test skips with a clear reason when the env var is absent.
- [ ] Focused unit tests cover the citation-gating behavior without network access.
- [ ] Existing offline browser tests and answer tests still pass.

## Out of Scope

- Redesigning retrieval, reranking, OCR, or the QA page UI.
- Adding a new model vendor SDK.
- Persisting raw user questions or raw model prompts outside existing request handling.
- Pushing to GitHub.
