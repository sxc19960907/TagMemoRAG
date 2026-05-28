# RAG configuration onboarding cards

## Goal

Extend the browser readiness guide with configuration onboarding cards so users can understand whether the key RAG capabilities are configured: answer LLM, embeddings, OCR, and PDF source previews.

The page should explain "what is enabled, what is missing, and what to do next" without requiring CLI commands or exposing secrets.

## Confirmed Facts

- `/admin/rag-readiness` already has a polished onboarding guide and summary API.
- Provider probes exist for live external checks, but they may call remote services and are not appropriate for page load by default.
- Manual diagnostics already expose OCR and source preview status without leaking raw document text.
- Config objects expose answer provider, embedding provider, OCR settings, and document asset settings.
- Existing conventions require API keys to be referenced by env var name only, never raw secret values.

## Requirements

- Add readiness summary capability/configuration cards for:
  - Answer LLM
  - Embeddings
  - OCR
  - PDF source previews
- Cards must be based on local configuration and local availability checks only. Do not call external model/provider APIs during page load.
- Show safe fields only: provider names, model ids, enabled flags, env var names, env-present booleans, OCR command availability, and source-preview renderer availability.
- Add recommendations when a configured capability is missing a required env var or local command.
- Render the capability cards as a distinct section in the readiness guide, visually readable and linked to relevant next actions.
- Preserve the existing `rag_readiness.v1` fields and add only backward-compatible fields.
- Add unit and browser coverage.

## Acceptance Criteria

- [ ] `/admin/rag-readiness/summary` includes a `capabilities` list with safe status/detail payloads.
- [ ] Missing answer/embedding env vars are reported by env var name and presence flag, not secret values.
- [ ] OCR cards report missing local commands when `ocr.provider=tesseract_cli`.
- [ ] PDF source preview cards report whether assets/page snapshots and renderer are available.
- [ ] The browser readiness page renders capability cards with clear statuses and next-action hints.
- [ ] Browser tests verify the configuration guide appears and does not leak unsafe internal fields.
- [ ] Existing readiness and QA browser flows remain stable.

## Out of Scope

- Running live provider probes from the readiness page.
- Editing `.env` or writing configuration files from the browser.
- Adding new provider SDKs.
- Pushing to GitHub.
