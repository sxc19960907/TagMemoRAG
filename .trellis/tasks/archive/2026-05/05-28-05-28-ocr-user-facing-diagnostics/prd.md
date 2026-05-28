# OCR user-facing diagnostics

## Goal

Make OCR status and prerequisites visible to browser users, add a local Tesseract smoke test, and document minimal OCR setup.

## Requirements

- Extend Manual Library diagnostics with a bounded OCR status summary derived from KB metadata and current settings.
- Show browser users whether OCR is disabled, enabled, attempted, created OCR chunks/pages, or failed without exposing OCR text.
- Add clearer recovery recommendations for scanned PDFs: enable OCR when missing-text PDF pages were found without OCR output; check/install OCR commands when `tesseract_cli` is enabled but prerequisites are missing.
- Preserve default-off OCR behavior and keep OCR command checks local/static.
- Add a local-only real Tesseract smoke test that skips cleanly when `tesseract` or `pdftoppm` is absent.
- Document the minimal OCR setup path: English OCR via `brew install tesseract`; avoid full `tesseract-lang` unless extra languages are required.

## Acceptance Criteria

- [x] `/manual-library/diagnostics` includes an `ocr` object with safe fields for enabled/provider/language/attempted/created/skipped/failed and command prerequisite status when applicable.
- [x] Manual Library diagnostics UI renders OCR status in a user-readable card alongside PDF quality.
- [x] Diagnostics recommendations distinguish missing OCR output from generic PDF parser quality warnings.
- [x] Real Tesseract smoke test passes locally when commands are available and skips in CI/offline environments without failing the suite.
- [x] README or docs explain the minimal Homebrew install, language defaults, and when `tesseract-lang` is needed.
- [x] Existing OCR, parser, diagnostics, and Manual Library UI tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

## Verification Notes

- Added bounded `last_rebuild.ocr` diagnostics with settings-derived enabled/provider/language/trigger plus rebuild-meta attempted/created/skipped/failed/failure reason counts.
- Added static local OCR command prerequisite checks for `ocr.provider=tesseract_cli`.
- Manual Library Operations now renders an OCR status card and recovery recommendations for enabling OCR, missing OCR commands, or OCR producing no indexed pages.
- Added a local real Tesseract smoke test that skips when `pdftoppm`, `tesseract`, or the generated scanned sample is absent.
- Updated README with minimal Homebrew setup, language defaults, and `tesseract-lang` caution.
- Validation: `uv run pytest tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py tests/unit/test_ocr_provider.py tests/unit/test_ocr_config.py -q` passed with 58 tests.
