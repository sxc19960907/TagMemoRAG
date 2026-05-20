# T9 Phase 8 connectors kickoff

## Goal

Ship the Phase 8 connector foundation: non-file or generated sources can be
normalized into the existing manual-library document pipeline without becoming a
parallel retrieval/indexing system. T9 establishes connector contracts,
deterministic local provider tests, and safe materialization into documents plus
metadata sidecars.

## Requirements

- Connectors are disabled by default.
- Define vendor-neutral connector dataclasses/protocols.
- Ship a deterministic local connector provider for tests; no network or SaaS
  credentials in default tests.
- Connector output materializes to supported local document files (`.md`, `.txt`,
  `.pdf`) plus `.metadata.json` sidecars under a KB staging directory.
- Materialized documents then use existing parser/chunker/index/retrieve/answer
  paths.
- Connector sync summaries must avoid raw document text, credentials, remote
  URLs with secrets, and high-cardinality local absolute paths.
- Unknown remote structures should be preserved as bounded opaque metadata or
  warnings, not crash the sync by default.
- Soft delete MVP uses tombstone status (`status="deleted"`) rather than
  physical deletion.
- ACL mapping is deferred; connector metadata may carry opaque ACL hints but
  retrieval enforcement is out of scope.

## Decisions

### D1 MVP: materialize, then reuse existing build

Connector records become normal files and metadata sidecars. The existing
`build_kb()` path remains authoritative.

### D2 Provider scope: deterministic local provider only

T9 ships a fixture-backed provider and factory. Production connectors such as
Notion/Confluence/SharePoint are follow-up tasks.

### D3 Sync mode: pull/poll snapshot

The MVP is an explicit pull-style sync that returns a snapshot of records.
Webhooks are deferred.

### D4 Delete semantics: tombstone

Remote deletes materialize metadata with `status="deleted"` so rebuild paths can
remove/deactivate content through existing manual status behavior.

## Out Of Scope

- Real SaaS connectors and auth flows.
- Credential storage/rotation.
- Webhook ingestion.
- Connector-specific ACL enforcement.
- Non-document binary conversion beyond supported document suffixes.
- UI surfaces for connector management.

## Acceptance Criteria

- [x] `Settings.connectors` exists and defaults to disabled.
- [x] Connector protocol, record, document, and sync summary contracts exist.
- [x] Deterministic fixture provider can produce create/update/delete records.
- [x] Materializer writes safe local files plus metadata sidecars.
- [x] Unsupported document suffixes and invalid records produce bounded failures.
- [x] Tombstone records materialize `status="deleted"`.
- [x] A materialized connector document can be indexed and retrieved through
      existing `build_kb()` / `/retrieve` behavior.
- [x] Focused connector tests and existing unit tests pass.

## Eval Slice

- Synthetic connector record with Markdown content answerable by `/retrieve`.
- Synthetic tombstone record that is skipped by rebuild.
- Existing parser/storage/API regression tests.
