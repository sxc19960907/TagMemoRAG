# Quality Guidelines

> Code quality standards for TagMemoRAG backend development.

---

## Overview

TagMemoRAG should be implemented as a small, testable Python package. Prefer explicit dataclasses, typed function signatures, deterministic tests, and narrow module boundaries.

M0 quality is defined by the acceptance criteria in `.trellis/tasks/05-10-wave-rag-implementation/prd.md` and the phase checklist in `implement.md`.

---

## Required Patterns

- Keep pure algorithm modules side-effect-free where practical.
- Use dataclasses for core contracts: `Chunk`, `Anchor`, `Result`, and `GraphState`.
- Normalize embeddings once and treat dot product as cosine similarity.
- Keep graph node ids as integers and store stable identity separately as `anchor_key`.
- Store vectors outside the NetworkX graph.
- Use atomic file replacement for persistent files.
- Keep rebuild double-buffer behavior: build new state off to the side, then swap only after success.
- Include `build_id` in search results and relevant logs.
- Use explicit config objects instead of scattering constants across modules.

---

## Forbidden Patterns

- Do not use pickle for persisted graph state.
- Do not let `/search` mutate graph, anchors, config, or storage.
- Do not make algorithm modules import FastAPI, CLI, or global app state.
- Do not make rebuild failures replace or clear the currently served graph.
- Do not silently drop unresolved anchors after rebuild.
- Do not introduce new production dependencies without updating `pyproject.toml`, tests, and this spec if behavior changes.
- Do not hand-roll string parsing for JSON/YAML/NPZ files when standard libraries or project storage helpers are available.

---

## Testing Requirements

M0 requires focused tests for:

- Parser edge cases: empty file, no headings, nested headings, long-block split, short-block merge.
- Embedder shape and normalization. Use a fake embedder in unit tests when model download would be too expensive.
- Graph builder semantic, parent-child, sibling, and consecutive edges.
- Wave search max vs sum aggregation, anchor boost, propagation boost, and deterministic ranking.
- Storage round-trips for graph, vectors, anchors, and meta.
- AppState rebuild concurrency: searches keep using old graph while rebuild runs.
- API error format and anchor/rebuild/search paths.
- E2E coffee-machine fixture queries, including `"蒸汽很小"`.

Tests should avoid network access by default. Heavy model tests should be opt-in or use fixtures/mocks unless the task explicitly requires real model verification.

---

## Code Review Checklist

- Does the change preserve the layer boundaries from `design.md`?
- Are config defaults centralized?
- Are API, CLI, and tests using the same data contracts?
- Are errors returned as `{code, message, detail}`?
- Are storage writes atomic?
- Does rebuild failure leave the old state intact?
- Are new files covered by unit or E2E tests proportional to risk?
- Did the implementation avoid scope creep from M1-M4?

---

## Common Mistakes

- Optimizing for future HA before M0 is correct.
- Baking default paths or thresholds into several modules.
- Testing only happy-path search while missing rebuild and storage failure paths.
- Treating `node_id` as stable across rebuilds.
- Forgetting that `implement.jsonl` and `check.jsonl` determine what future agents automatically load.
