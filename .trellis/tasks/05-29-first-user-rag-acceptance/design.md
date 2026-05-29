# Design

## Approach

Treat this task as an acceptance-and-hardening pass rather than a new feature build. The primary artifact is a black-box acceptance record that follows the same path a new evaluator would follow:

1. Read public entry points.
2. Start the documented local profile.
3. Open browser pages.
4. Upload and index real sample documents.
5. Ask questions and inspect cited sources.
6. Switch languages and confirm the page remains usable.
7. Run focused browser and quality tests.

Any implementation changes should be limited to gaps discovered during this path, such as stale docs, mismatched button labels, missing UI copy, fragile tests, or small recovery hints.

## Boundaries

- Public docs and README are user-facing product entry points.
- Browser pages are the user-facing acceptance surface.
- Existing API/service behavior should remain unchanged unless the acceptance pass exposes a real user-visible defect.
- Tests should reuse existing browser helpers where possible.

## Data Flow Under Test

Document file -> Manual Library or Q&A upload form -> validation -> blob/manual registry -> rebuild/index -> `/answer` -> Q&A answer bubble -> citation chips -> source cards -> safe preview/source verification links.

The acceptance pass should pay attention to boundary leaks: storage keys, blob keys, local paths, raw diagnostics, checksums, or parser internals must not appear in normal user-facing Q&A source cards.

## Compatibility

- Default local demo remains offline and deterministic with hashing embeddings and noop answers.
- Existing docs still point to the same local URLs.
- Existing opt-in browser tests remain opt-in.
- OCR remains optional and skipped cleanly when local tools/sample are absent.

## Rollback

If a proposed fix expands beyond docs/UI/test hardening, split it into a later task. This task should stay shippable even if no code changes are required beyond acceptance artifacts.
