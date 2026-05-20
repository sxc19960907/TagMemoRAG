# Provider live probe

## Goal

Add an explicit operator command for live provider connectivity checks after `config validate` has confirmed static/local prerequisites.

This task closes the remaining deployment-readiness gap: static config can be coherent while remote services, credentials, or endpoints are still unusable. The live probe must be opt-in and safe by default because it can call external services.

## Confirmed Facts

- `config validate` now checks static config, local paths, env var names, and optional dependency imports without network calls.
- `readiness smoke` validates deterministic local MVP paths without remote providers.
- Existing provider clients already implement the actual transports:
  - `HttpEmbedder` for OpenAI-compatible embeddings
  - `OpenAICompatibleAnswerGenerator` for chat completions
  - `SFQwen3Reranker` for SiliconFlow rerank
  - `QdrantVectorStore` / `qdrant_ops.inspect_qdrant`
  - S3 client construction in `manual_blob_store`
- Provider code already avoids putting secret values in config; keys are read from named env vars.

## Requirements

- Add `tagmemorag provider probe --config <path>`.
- The command must be explicit opt-in and must not run as part of `config validate`, `readiness smoke`, startup, build, or tests unless directly invoked.
- Support provider selectors:
  - `--embedding`
  - `--answer`
  - `--reranker`
  - `--qdrant`
  - `--s3`
  - `--all`
- Return JSON by default with stable schema version, aggregate `status`, and per-probe entries.
- Per-probe statuses: `passed`, `warning`, `failed`, `skipped`.
- Skip probes when the related provider is not configured/enabled, unless the user explicitly selected that provider; explicit selection should return `failed` if the config cannot support the probe.
- Use minimal requests:
  - embedding: encode one short probe string and verify vector shape
  - answer: one tiny chat-completions request with no retrieved context dependency
  - reranker: one query and two tiny docs
  - qdrant: collection/info call through existing client boundary
  - s3: bucket head call through configured client
- Use short timeouts derived from config with an upper clamp so probes do not hang.
- Never print secret values, Authorization headers, raw provider response bodies, generated answer text, raw embeddings/vectors, raw document text, or object keys beyond bounded configured names.
- Tests must avoid real network by using fake clients/monkeypatches.

## Acceptance Criteria

- [ ] `tagmemorag provider probe --config ... --embedding` can report a passed fake embedding probe.
- [ ] Missing config/env for an explicitly selected remote provider fails with env var name only.
- [ ] Unconfigured provider probes are skipped when using `--all`.
- [ ] Qdrant and S3 probes are covered through fake clients or monkeypatches with no live services.
- [ ] CLI exit code is `0` only when aggregate status is `passed`, `warning`, or all selected probes are `skipped`; exit code is `1` when any selected probe fails.
- [ ] README/ops docs explain the difference between `config validate`, `readiness smoke`, `/ready`, and `provider probe`.
- [ ] Final validation includes focused provider/CLI tests and `git diff --check`.

## Out Of Scope

- Periodic monitoring or background health checks.
- Automatic provider probing during server startup.
- Full quality/eval scoring.
- Printing provider payloads or generated content.
- Retrying enough to hide intermittent provider failures.
- Supporting production OCR/visual providers, which are not implemented yet.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
