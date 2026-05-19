# T1.5 IndexGeneration derivatives isolation — Implementation Checklist

## Pre-flight

- [x] Active task = `05-19-t15-indexgen-derivatives-isolation`.
- [x] Read PRD/design and backend specs.
- [x] Start task.

## Slice 1 — Path parameters

- [x] Add optional path override to EPA basis helpers.
- [x] Add optional path override to tag cooccurrence helpers.
- [x] Add optional `paths` to `sync_rebuild_tags`.
- [x] Tests for legacy and generation path routing.

## Slice 2 — Generation wiring

- [x] Generation-oriented callers can pass `KbPaths`.
- [x] Ensure legacy full/incremental callers remain unchanged.
- [x] Tests for generation derivative outputs.

## Slice 3 — Spec + validation

- [x] Update architecture T1.5 status.
- [x] Run focused and full unit tests.
