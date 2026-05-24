# Implementation Plan

## Steps

- [x] Add `src/tagmemorag/same_page_ordering.py` with pure ordering helpers.
- [x] Add `SearchConfig` fields and env/YAML tests.
- [x] Wire `build_retrieve_response` to accept optional same-page ordering
      options and keep default behavior unchanged.
- [x] Wire `/retrieve` call site to pass options from `settings.search`.
- [x] Add retrieval tests for disabled, enabled, and rank-1 preservation.
- [x] Run focused tests:
      `.venv/bin/pytest tests/unit/test_retrieval.py tests/unit/test_config_env.py tests/unit/test_same_page_ordering_candidate.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] Run the batch gate.
- [ ] Update parent program log.
- [ ] Commit and archive this child.

## Review Gates

- Default-off behavior must be unchanged.
- No external provider calls or network access.
- No generated `.tmp/` reports committed.
- No raw query/snippet diagnostics added.
- Gate remains passed.

## Eval Slice

Runtime code is unit-tested directly. The retained general-web candidate dry
run remains the acceptance baseline for any future default-on proposal.
