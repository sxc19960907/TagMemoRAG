# Implementation Plan

## Scope

- Documentation and code comments/docstrings only.
- No retrieval behavior, config defaults, API schemas, or test fixtures change.

## Steps

- [x] Update README overview and WAVE/operator sections.
- [x] Update WAVE Phase 1 / Phase 4 code-level descriptions.
- [x] Mark T4 shipped in the architecture roadmap.
- [x] Run validation grep and focused tests for config/search docs-sensitive areas.
- [ ] Archive and journal after commit.

## Validation

```bash
rg -n "production-grade|Strengths Worth Preserving" README.md docs src/tagmemorag .trellis/spec/backend -S
uv run pytest tests/unit/test_config_env.py tests/unit/test_search_runtime_phase1.py tests/unit/test_geodesic_rerank.py tests/unit/test_graph_wave.py -q
git diff --check
```
