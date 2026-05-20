# DeepSeek answer budget citation compliance

## Goal

Reduce the two DeepSeek `/answer` gaps exposed by the real PDF rerun: too-small default output budget for the production-provider profile, and missing validated citations when a provider emits citation ids only in answer text.

## Requirements

- Keep global `/answer` defaults conservative unless the profile explicitly opts into a larger budget.
- Set the production-provider verification profile to a DeepSeek-safe answer budget.
- Extract valid citation ids from OpenAI-compatible answer text when providers do not return a structured `message.citations` field.
- Continue to validate citations against the retrieve payload allowlist; do not accept invented citation ids.
- Keep provider responses, raw answer text, secrets, and retrieved snippets out of committed docs.

## Acceptance Criteria

- [x] `examples/config/production-provider-verification.yaml` uses an answer budget that avoids the observed DeepSeek 128-token failure path.
- [x] OpenAI-compatible answer parsing extracts bracketed allowed-looking citation ids from answer text.
- [x] Citation validation still drops unknown ids.
- [x] Unit tests cover text-only citation extraction and invalid-citation dropping.
- [x] Full unit/e2e test suite passes.
