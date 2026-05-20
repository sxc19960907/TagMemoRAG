# Provider Live Probe — Implementation Plan

- [x] Read backend specs and shared guides.
- [x] Add `src/tagmemorag/provider_probe.py` with:
  - report/check dataclasses
  - selector handling
  - safe detail/error sanitization
  - probe functions for embedding, answer, reranker, qdrant, s3
- [x] Wire `tagmemorag provider probe` in `cli.py`.
- [x] Add tests for:
  - embedding fake pass
  - missing env/config failure
  - `--all` skipped providers
  - qdrant fake pass/failure
  - s3 fake pass/failure
  - CLI JSON and exit codes
- [x] Update README and production operations guide.
- [x] Run focused tests:
  - `uv run pytest tests/unit/test_cli.py tests/unit/test_config_env.py -q`
- [x] Run actual safe local command with a non-remote config:
  - `uv run python -m tagmemorag provider probe --config examples/config/local-hashing-npz.yaml --all`
- [x] Run `git diff --check`.
- [ ] Commit, archive, and journal.

## Risk Notes

- Do not run live probes from any default path.
- Never print secret values, headers, vectors, response bodies, or generated answer text.
- Tests must not depend on network or real credentials.
- Keep timeout small and bounded.

## Results

- Added `tagmemorag provider probe` with `--embedding`, `--answer`, `--reranker`, `--qdrant`, `--s3`, and `--all`.
- Added `provider_probe.v1` JSON reports with `passed`, `warning`, `failed`, and `skipped` per-probe statuses.
- Implemented live probe paths for configured embedding, answer, reranker, Qdrant, and S3 providers while keeping local/default providers skipped under `--all`.
- Tests use fake/monkeypatched provider boundaries only; no default test performs network access.
- Updated README and production operations guide with the four readiness layers: `config validate`, `provider probe`, `readiness smoke`, and `/ready`.

## Verification

- `uv run pytest tests/unit/test_cli.py tests/unit/test_config_env.py -q` -> 60 passed.
- `uv run python -m tagmemorag provider probe --config examples/config/local-hashing-npz.yaml --all` -> status `skipped` for all remote providers.
- `git diff --check` -> passed.
