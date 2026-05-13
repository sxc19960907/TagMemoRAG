# implement.md - M22 Qdrant Operations Documentation and Inspection Tools

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Review existing Qdrant backend, fake client tests, M21 recovery status, and README Qdrant section.
- [ ] Update README Qdrant operations docs with setup, config, collection naming, payload contract, rebuild sync, M18 batch payload note, M21 recovery status, inspection, and rollback commands.
- [ ] Decide whether to implement CLI inspection in M22 or keep it docs-only.
- [ ] If implementing inspection, add a small read-only report helper.
- [ ] Add CLI command, recommended shape: `python -m tagmemorag qdrant inspect --kb default --config config.yaml`.
- [ ] Ensure inspection output is JSON, low-cardinality, and free of raw vectors/text/payload dumps.
- [ ] Add fake-client unit tests for collection/count/payload-key/missing-vector/non-Qdrant cases.
- [ ] Preserve existing Qdrant load compatibility and rebuild sync ordering.
- [ ] Verify README examples match actual CLI/config names.
- [ ] Curate `implement.jsonl` and `check.jsonl` with relevant specs/research before implementation if using sub-agents.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_storage_state.py tests/unit/test_manual_library.py tests/unit/test_cli.py tests/unit/test_api.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

Manual smoke commands:

```bash
uv run python -m tagmemorag manual-library dirty --kb default --config config.yaml --format json
uv run python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode incremental
uv run python -m tagmemorag manual-library rebuild --kb default --config config.yaml --mode full
uv run python -m tagmemorag qdrant inspect --kb default --config config.yaml
```

The `qdrant inspect` smoke command applies only if the command is implemented.

## Review Gates

- Confirm the inspection report is additive and read-only.
- Confirm report fields are bounded and safe.
- Confirm legacy payloads are recommendations, not load-breaking failures.
- Confirm no default test requires a live Qdrant server.
- Confirm M15-M18 Qdrant failure-ordering and payload-refresh tests still pass.
- Confirm README commands are copyable and match implemented CLI flags.

## Rollback Points

- If CLI inspection becomes too broad, defer the command and complete M22 as documentation only.
- If real-client payload sampling is awkward or costly, report point counts and missing vectors first; defer payload coverage.
- If API inspection is requested during implementation, document it as follow-up unless the CLI helper makes it trivial and safe.
