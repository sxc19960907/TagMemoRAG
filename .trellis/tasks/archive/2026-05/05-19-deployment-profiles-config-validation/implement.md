# Deployment Profiles And Config Validation — Implementation Plan

- [x] Read backend specs and shared guides.
- [x] Add `src/tagmemorag/config_validation.py` with safe report objects and validation rules.
- [x] Wire `tagmemorag config validate --config ...` in `cli.py`.
- [x] Add example profiles under `examples/config/`.
- [x] Add focused tests for:
  - healthy local profile pass
  - missing remote env failure
  - missing optional extra warning
  - S3 missing bucket failure
  - CLI exit codes and JSON shape
  - example profiles load
- [x] Update README and production operations guide.
- [x] Run focused tests:
  - `uv run pytest tests/unit/test_config_env.py tests/unit/test_cli.py -q`
- [x] Run `git diff --check`.
- [ ] Commit, archive, and journal.

## Risk Notes

- Do not print secret values; env var names are okay.
- Do not perform network checks in this task.
- Path checks should be local and low impact; only create directories in temp/test or operator-selected local paths when validating.
- Validation should not claim a profile is production-ready; it only proves static coherence and local prerequisites.

## Results

- Added `tagmemorag config validate --config ...` with JSON report schema `config_validation.v1`.
- Added safe validation for config load, local writable paths, remote provider env var presence by env-name only, optional extras, S3 bucket configuration, and auth/metrics posture.
- Added example config profiles:
  - `examples/config/local-hashing-npz.yaml`
  - `examples/config/local-sqlite-registry.yaml`
  - `examples/config/qdrant.yaml`
  - `examples/config/s3-blob.yaml`
  - `examples/config/answer-openai-compatible.yaml`
- Updated README and production operations guide to explain profile validation versus readiness smoke versus `/ready`.

## Verification

- `uv run pytest tests/unit/test_config_env.py tests/unit/test_cli.py -q` -> 53 passed.
- `uv run python -m tagmemorag config validate --config examples/config/local-hashing-npz.yaml` -> passed.
- `uv run python -m tagmemorag config validate --config examples/config/answer-openai-compatible.yaml` -> failed as expected without `OPENAI_API_KEY`, reporting only the env var name.
- `git diff --check` -> passed.
