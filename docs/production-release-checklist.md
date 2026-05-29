# Production Release Checklist

Use this checklist before opening TagMemoRAG to a broader trial or production-like pilot. It summarizes the operator flow and links to the deeper runbooks for exact commands.

## 1. Preflight

- Confirm the target profile and config file.
- Run static config validation.
- Run the local deterministic readiness smoke.
- Run the focused quality tier for the change, then check GitHub Actions after push.
- Record the release version, commit hash, config profile, and verification directory.

References:

- [Production Environment Verification](production-environment-verification.md)
- [RAG Quality Gates](rag-quality-gates.md)

## 2. Backup And Restore

- Identify every durable store in use: graph artifacts, QueryPlan SQLite, manual registry, blob store, Qdrant collections, config templates, and secrets.
- Export a manual-library bundle before migration, release, or destructive maintenance.
- Test bundle inspect/import into a non-production target KB.
- If using SQLite, take a SQLite-safe backup or checkpoint-aware copy.
- If using S3 or Qdrant, use the provider's native backup/snapshot tooling and keep the TagMemoRAG bundle as the source-document recovery path.

References:

- [Production Deployment And Operations](production-deployment-operations.md#persistence-matrix)
- [Production Deployment And Operations](production-deployment-operations.md#bundle-restore-and-migration)

## 3. Access And Permissions

- Enable auth for non-local deployments.
- Keep `/health`, `/ready`, and `/metrics` public only when your network boundary allows it.
- Give normal Q&A users `search` only.
- Give document maintainers `search` and `rebuild`.
- Reserve `admin` for people who manage tokens, hard delete documents, or triage feedback.
- Store provider keys in environment variables or a secret manager; do not put raw secrets in YAML, docs, retained reports, screenshots, or shell history captures.

References:

- [Production Deployment And Operations](production-deployment-operations.md#configuration-and-secrets)
- [Trial Operator Handoff](trial-operator-handoff-2026-05-27.md)

## 4. Live Provider And Storage Checks

- Run only the live probes that match the enabled providers.
- Verify Qdrant and S3 only when the target profile uses them.
- Verify answer/reranker providers only when those providers are part of the release.
- Keep provider-probe output bounded: no Authorization headers, raw response bodies, generated answer text, vectors, or raw document chunks.

References:

- [Production Environment Verification](production-environment-verification.md#live-provider-probes)
- [Production Provider Smoke Runbook](production-provider-smoke-runbook.md)

## 5. Browser Acceptance

- Open Manual Library and confirm the target KB has no unexpected pending rebuild.
- Upload or restore a real manual, rebuild, and verify searchable state.
- Ask in Q&A and inspect citation chips plus source cards.
- For real PDFs, verify source preview links are safe `/assets/...` URLs and do not expose storage keys, blob keys, checksums, node IDs, or anchor keys.
- Switch language once and confirm the user-facing page remains coherent.

References:

- [Browser RAG Quick Start](browser-rag-quick-start.md)
- [Real PDF And Document Intake Test](real-pdf-document-intake-test-2026-05-27.md)

## 6. Monitoring And Evidence

- Capture `/health`, `/ready`, and `/metrics` after the service starts.
- Capture manual-library dirty state, registry/blob verification, and diagnostics.
- Retain the pilot report and production verification summary in a dated evidence directory.
- Review artifacts before sharing them outside the operations team. They are designed to avoid secrets and raw document text, but deployment paths and service names may still be sensitive.

References:

- [Production Environment Verification](production-environment-verification.md#evidence-directory)
- [Production Pilot Runbook](production-pilot-runbook.md)

## 7. Rollback

- For bad config, restore the previous config/env and restart.
- For failed rebuild, keep serving the old graph, inspect dirty state, fix the reported cause, and retry.
- For Qdrant outage, restore Qdrant or switch to local NPZ and rebuild from managed sources.
- For S3/blob outage, restore bucket/prefix/network/credentials and verify blobs before rebuild.
- For bad bundle import, inspect/import into a clean target or restore from backup before rebuilding production.

References:

- [Production Deployment And Operations](production-deployment-operations.md#rollback-playbooks)

## Release Decision

Proceed only when:

- Required checks have passed or have an explicitly accepted warning.
- Backup and restore paths are known for the active profile.
- Auth scopes match the intended user roles.
- Browser Q&A produces cited answers on real documents.
- Operators know how to roll back config, rebuild, Qdrant, S3/blob, and bundle-import issues.
