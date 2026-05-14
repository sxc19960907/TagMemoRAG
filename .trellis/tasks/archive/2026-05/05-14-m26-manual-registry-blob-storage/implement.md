# implement.md - M26 Manual Registry and Pluggable File Storage

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Add registry/blob-store context to `implement.jsonl` and `check.jsonl`.
- [ ] Add config fields for registry and blob-store mode.
- [ ] Implement `manual_blob_store.py` with `BlobRef`, protocol/base class, and local backend.
- [ ] Implement `manual_registry.py` with SQLite schema creation, transactional CRUD, and audit event writes.
- [ ] Add unit tests for registry create/update/delete/list, uniqueness, transactions, and audit events.
- [ ] Add unit tests for local blob put/get/exists/delete, checksum, and safe key generation.
- [ ] Add sidecar-to-registry migration dry-run and commit path.
- [ ] Route `manual_library` facade through registry/blob-store when `registry_backend=sqlite`.
- [ ] Preserve existing file-sidecar behavior when `registry_backend=file`.
- [ ] Add registry-backed rebuild staging and cleanup on success/failure.
- [ ] Verify failed blob reads/rebuilds do not clear dirty state or swap active graph.
- [ ] Add CLI inspection/migration/verify-blobs commands.
- [ ] Add additive API/admin response fields where useful and safe.
- [ ] Update README with local default, SQLite registry mode, migration, rollback, and S3-compatible roadmap.
- [ ] Update backend specs if registry/blob-store contracts become durable conventions.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_bulk_import_api.py tests/unit/test_tag_suggestions.py -q
uv run pytest tests/unit/test_config_env.py tests/unit/test_api.py tests/unit/test_cli.py -q
```

New tests to add:

```bash
uv run pytest tests/unit/test_manual_registry.py tests/unit/test_manual_blob_store.py -q
uv run pytest tests/e2e/test_manual_registry_rebuild.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm file-sidecar mode remains unchanged by default.
- Confirm registry mode does not store raw document content in SQLite.
- Confirm blob keys do not expose absolute machine paths.
- Confirm audit details are bounded and safe.
- Confirm migration is idempotent and dry-run capable.
- Confirm rebuild failure leaves dirty state pending and old graph active.
- Confirm S3-compatible design does not require live object storage in default tests.

## Rollback Points

- If registry migration proves too invasive, ship only blob-store abstraction plus local backend first.
- If rebuild staging causes unacceptable duplication, keep M26 at registry/blob upload path and defer registry-backed rebuild to M27.
- If SQLite schema churn grows, freeze MVP schema and add explicit `schema_version` migration hooks before expanding audit details.
