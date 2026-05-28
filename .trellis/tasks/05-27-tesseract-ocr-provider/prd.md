# Tesseract OCR Provider

## Goal

Add a default-off production OCR provider that can turn missing-text PDF pages into text through local command-line OCR tooling, without changing the existing deterministic test provider or default runtime behavior.

## User Value

Users will eventually upload scanned/image-only PDFs. The system already knows when PDF pages have no native text and has an OCR provider interface; adding a real local provider makes OCR usable on operator machines that install Tesseract/Poppler while preserving stable behavior everywhere else.

## Confirmed Facts

- `Settings.ocr.enabled` defaults to `False` and `provider` currently only accepts `deterministic`.
- The parser invokes OCR only for PDF pages where native `pypdf` extraction produces no usable lines.
- OCR output already becomes normal chunks with `ocr_provider`, `ocr_version`, `ocr_trigger`, and `ocr_source` lineage.
- `config validate` checks optional Python dependencies but currently does not check OCR system commands.
- The project currently has no OCR Python dependencies and should avoid adding heavyweight OCR packages in this slice.

## Requirements

- Add an opt-in `tesseract_cli` OCR provider.
- Render only the requested PDF page to an image through a configurable command-line renderer, defaulting to `pdftoppm`.
- Run OCR through a configurable command-line OCR binary, defaulting to `tesseract`.
- Keep OCR default-off and keep the deterministic provider working.
- Bound runtime with `timeout_seconds`, `dpi`, and page-scoped temp files.
- Return OCR text through the existing `OCRPageResult` contract.
- On missing commands, timeouts, or command failures:
  - in normal OCR mode, provider exceptions should be summarized by existing parser OCR failure handling;
  - in strict mode, parser behavior remains fail-fast through the existing `ocr_strict` path.
- `config validate` should report OCR system-command availability when `ocr.enabled=true` and `ocr.provider=tesseract_cli`.
- Do not add heavy production OCR Python dependencies.
- Add focused unit tests with mocked command execution; do not require local Tesseract/Poppler in CI.

## Acceptance Criteria

- [ ] `Settings(ocr.provider="tesseract_cli")` is valid.
- [ ] `create_ocr_provider()` returns a Tesseract CLI provider when enabled.
- [ ] Provider renders only the requested PDF page and runs OCR on the rendered image.
- [ ] OCR text is returned as `OCRPageResult.text`.
- [ ] Missing/failed commands produce bounded failures that existing parser OCR summary captures.
- [ ] `config validate` warns/fails clearly about missing `pdftoppm` or `tesseract` when the provider is enabled.
- [ ] Deterministic provider tests remain green.
- [ ] Focused OCR/config/parser tests pass.
- [ ] `git diff --check` passes.

## Out Of Scope

- PaddleOCR/EasyOCR/cloud OCR providers.
- Installing system packages automatically.
- Layout-aware table/region OCR, bounding boxes, confidence scoring, or image OCR outside PDF missing-text pages.
- Enabling OCR by default.
- Browser UI for configuring OCR binaries.
