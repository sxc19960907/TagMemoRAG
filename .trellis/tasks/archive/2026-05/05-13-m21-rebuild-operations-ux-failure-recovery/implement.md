# implement.md - M21 Rebuild Operations UX and Failure Recovery

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Review existing rebuild task payloads, manual-library dirty export, rebuild impact artifacts, API/CLI rebuild commands, and Qdrant fake-client failure tests.
- [ ] Add a small helper that derives an operator rebuild summary from task, manifest, current state, and config.
- [ ] Extend `GET /manual-library/dirty` JSON with pending/build/recovery fields while preserving existing keys.
- [ ] Extend `python -m tagmemorag manual-library dirty --format json` with the same fields, or add `manual-library status` if a separate command reads better during implementation.
- [ ] Add task-level summary fields to `GET /rebuild/{task_id}` and CLI `manual-library rebuild` output if they are not already clear enough.
- [ ] Add recovery hints/actions for common paths: inspect dirty, retry incremental, force full rebuild, check Qdrant, switch to NPZ.
- [ ] Preserve CSV column order for `manual-library dirty --format csv`.
- [ ] Add tests for API dirty/status output after pending changes and after rebuild failure.
- [ ] Add tests for CLI dirty/status output and rebuild failure output.
- [ ] Add or extend fake-Qdrant tests to cover full rebuild recovery after failed incremental/payload sync.
- [ ] Update README with a short rebuild recovery runbook.
- [ ] Verify no output includes raw vectors, raw chunk text, secrets, candidate id lists, or raw Qdrant payload dumps.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py tests/unit/test_cli.py tests/unit/test_api.py -q
```

Related storage/search checks:

```bash
uv run pytest tests/unit/test_storage_state.py tests/unit/test_cache.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

Manual smoke commands:

```bash
uv run python -m tagmemorag manual-library dirty --kb default --config config.yaml --format json
uv run python -m tagmemorag manual-library dirty --kb default --config config.yaml --format csv
uv run python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode incremental
uv run python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode full
```

## Review Gates

- Confirm the response shape is additive and backward compatible.
- Confirm recovery hints are derived from stable state, not brittle exception strings.
- Confirm dirty state still clears only after successful graph swap.
- Confirm failed Qdrant sync does not delete stale points before required upserts/payload refresh succeeds.
- Confirm status output is useful without requiring operators to read manifest or impact JSON files directly.

## Rollback Points

- If adding a new `status` command creates duplicate behavior, revert to extending `dirty` only.
- If recovery hint logic becomes too speculative, expose conservative `recovery_actions` and document the decision tree instead.
- If UI changes grow too large, keep M21 to API/CLI/docs and split UI polish into a follow-up task.
