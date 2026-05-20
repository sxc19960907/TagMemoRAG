# T7 Phase 7A OCR kickoff — Implementation Checklist

## Pre-flight

- [x] Active task = `05-19-t7-ocr-kickoff`.
- [x] Read PRD/design and backend specs.
- [x] Start task with `task.py start`.

## Slice 0 — Config + OCR contracts

- [x] Add `OCRConfig` to `config.py`.
- [x] Add `src/tagmemorag/ocr/base.py`.
- [x] Add deterministic provider and factory.
- [x] Tests for config and provider.

## Slice 1 — Parser OCR path

- [x] Add optional OCR provider/config params to `parse_document`.
- [x] Trigger OCR only for empty PDF pages.
- [x] Add OCR chunk metadata and parser profile.
- [x] Aggregate safe OCR summary.
- [x] Tests for disabled, missing-text, native skip, failure.

## Slice 2 — Rebuild integration

- [x] Wire provider creation into `build_kb`.
- [x] Store OCR summary in `state.meta["ocr"]` when enabled/attempted.
- [x] Tests that OCR-only text becomes searchable/retrievable.

## Slice 3 — Spec + validation

- [x] Update architecture B7A status/contract.
- [x] Run:

```bash
uv run pytest tests/unit/test_ocr_config.py \
  tests/unit/test_ocr_provider.py \
  tests/unit/test_parser.py \
  tests/unit/test_storage_state.py \
  tests/unit/test_api.py \
  tests/unit/test_answer_api.py -q
uv run pytest tests/unit -q
git diff --check
```

## Rollback

Additive: remove OCR package, config block, parser optional path, rebuild
summary wiring, tests, and B7A spec update. Native PDF parser remains unchanged.
