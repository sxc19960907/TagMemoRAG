# T8 Phase 7B visual retrieval kickoff — Implementation Checklist

## Pre-flight

- [x] Active task = `05-19-t8-visual-retrieval-kickoff`.
- [x] Read PRD/design and backend specs.
- [x] Start task with `task.py start`.

## Slice 0 — Config + contracts

- [x] Add `VisualRetrievalConfig` to `config.py`.
- [x] Add visual retrieval dataclasses/protocols.
- [x] Add deterministic provider and noop reranker factory.
- [x] Tests for config and provider.

## Slice 1 — Retrieve fusion

- [x] Extend retrieval assembly with optional visual provider context.
- [x] Keep disabled response unchanged.
- [x] Add visual-only evidence/context item shape.
- [x] Deduplicate assets already attached to text evidence.
- [x] Tests for disabled/enabled/non-visual/missing-manifest/dedupe.

## Slice 2 — API wiring

- [x] Wire settings/state asset manifest into `/retrieve` visual retrieval path.
- [x] API tests for visual-intent visual-only candidate and safe payload.

## Slice 3 — Spec + validation

- [x] Update architecture B7B status/contract.
- [x] Run:

```bash
uv run pytest tests/unit/test_visual_retrieval_config.py \
  tests/unit/test_visual_retrieval_provider.py \
  tests/unit/test_retrieval.py \
  tests/unit/test_api.py \
  tests/unit/test_answer_api.py \
  tests/unit/test_parser.py \
  tests/unit/test_storage_state.py -q
uv run pytest tests/unit -q
git diff --check
```

## Rollback

Additive: remove visual retrieval package, config block, retrieval/API optional
wiring, tests, and B7B spec update. Existing visual evidence attachment remains
unchanged.
