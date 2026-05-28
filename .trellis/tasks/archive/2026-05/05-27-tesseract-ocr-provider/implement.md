# Implementation Plan

## Checklist

- [x] Extend `OCRConfig` with `tesseract_cli` provider and command/runtime settings.
- [x] Implement `TesseractCliOCRProvider` using `pdftoppm` + `tesseract` command execution.
- [x] Wire `create_ocr_provider()` to return the new provider.
- [x] Add config validation checks for required system commands when enabled.
- [x] Add focused tests for config parsing, provider command construction/success, command failure, and parser summary behavior.
- [x] Update specs/docs for the default-off provider contract.
- [x] Run verification:
  - `python3 -m py_compile src/tagmemorag/config.py src/tagmemorag/ocr/provider.py src/tagmemorag/config_validation.py tests/unit/test_ocr_config.py tests/unit/test_ocr_provider.py tests/unit/test_config_validation.py tests/unit/test_parser.py`
  - `uv run pytest tests/unit/test_ocr_config.py tests/unit/test_ocr_provider.py tests/unit/test_config_validation.py tests/unit/test_parser.py -q`
  - `git diff --check`

## Rollback

Remove the config fields, provider class/factory branch, config validation checks, tests, and spec/doc updates. Existing deterministic OCR provider should be unchanged.

## Verification Notes

- Focused OCR/config/parser run passed: `11 passed`.
- Expanded related run passed: `83 passed`.
- `git diff --check` passed.
