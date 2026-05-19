# Implementation Plan

- [x] Read current Docker/config/README/docs and archived M26-M30 task contracts.
- [x] Add `docs/production-deployment-operations.md`.
- [x] Link the guide from README and update the roadmap/milestone table without renumbering historical M31.
- [x] Check guide language against backend specs and documented limits.
- [x] Run validation grep, `git diff --check`, and focused tests.
- [ ] Archive and journal after commit.

## Validation Commands

```bash
rg -n "leader election|built-in HA|automatic object-store backup|encrypted bundle|signed bundle|production-grade" docs/production-deployment-operations.md README.md -S
git diff --check
uv run pytest tests/unit/test_config_env.py tests/unit/test_manual_blob_store.py tests/unit/test_manual_library.py tests/unit/test_manual_bundle.py -q
```
