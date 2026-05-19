# T9 Phase 8 connectors kickoff — Implementation Checklist

## Pre-flight

- [x] Active task = `05-19-t9-connectors-kickoff`.
- [x] Read PRD/design and backend specs.
- [x] Start task.

## Slice 0 — Config + contracts

- [x] Add `ConnectorsConfig`.
- [x] Add connector dataclasses/protocol.
- [x] Add fixture provider/factory.
- [x] Tests for config/provider.

## Slice 1 — Materializer

- [x] Safe path validation.
- [x] Document + sidecar writes.
- [x] Tombstone metadata.
- [x] Summary/failure handling.
- [x] Tests for create/delete/invalid suffix.

## Slice 2 — Integration

- [x] Build/retrieve from materialized connector docs.
- [x] Update B8 architecture contract.
- [x] Run focused and full unit tests.
