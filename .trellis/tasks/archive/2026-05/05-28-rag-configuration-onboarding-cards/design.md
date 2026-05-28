# RAG Configuration Onboarding Cards Design

## Scope

This task adds a local configuration status layer to `/admin/rag-readiness`. It is deliberately not a live provider verification workflow. The goal is to guide the user before they run real Q&A, not to spend tokens or make network calls during page load.

## API Contract

`rag_readiness_summary(...)` adds:

```json
{
  "capabilities": [
    {
      "id": "answer",
      "title": "Answer LLM",
      "status": "ready|needs_review|not_ready",
      "summary": "...",
      "detail": {},
      "action": {"label": "...", "href": "...", "kind": "..."}
    }
  ]
}
```

Status semantics:

- `ready`: capability is locally configured/available enough for the relevant path.
- `needs_review`: optional capability is disabled or non-blocking configuration is incomplete.
- `not_ready`: capability is enabled/configured for a live path but a required local prerequisite is missing.

## Capability Rules

- Answer LLM:
  - ready when `answer.enabled` and `provider=openai_compatible` and `api_key_env` is present in the environment.
  - needs_review when answer generation is disabled or `noop`.
  - not_ready when openai-compatible answer is enabled but env var is missing.
- Embeddings:
  - ready for local/hashing providers.
  - ready for `http` only when the configured env var is present.
  - not_ready for `http` with missing env var.
- OCR:
  - needs_review when disabled.
  - ready when enabled deterministic.
  - for `tesseract_cli`, ready only when configured commands are available; otherwise not_ready.
- PDF source previews:
  - needs_review when document assets or page snapshots are disabled.
  - ready when enabled and renderer is available.
  - not_ready when enabled but renderer is missing.

## Frontend

`rag_readiness.html` adds a capability section after the setup steps and before readiness cards.

`rag_readiness.js` renders `body.capabilities` as compact cards. It should use curated fields and not render arbitrary nested objects.

`manual_library.css` adds scoped `.readiness-capabilities` styles that match the setup guide.

`i18n.js` adds Chinese translations for all new visible text.

## Safety

- Never expose raw env var values.
- Never render local absolute paths, storage keys, blob keys, checksums, raw manifest rows, node ids, or document text.
- Do not call live provider APIs.

## Validation

- Unit tests for summary payloads in local, missing-env, OCR command, and source preview scenarios.
- Browser test for visible capability cards and no unsafe leak strings.
