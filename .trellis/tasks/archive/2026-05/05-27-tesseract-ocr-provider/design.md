# Tesseract OCR Provider Design

## Design

Add a provider class under `src/tagmemorag/ocr/provider.py`:

```python
class TesseractCliOCRProvider:
    provider_name = "tesseract_cli"
    def recognize_pdf_page(self, context: OCRPageContext) -> OCRPageResult: ...
```

The provider stays behind `Settings.ocr.enabled` and `Settings.ocr.provider == "tesseract_cli"`.

## Config Contract

Extend `OCRConfig`:

- `provider: Literal["deterministic", "tesseract_cli"]`
- `tesseract_command: str = "tesseract"`
- `pdf_renderer_command: str = "pdftoppm"`
- `dpi: int = 200`
- `timeout_seconds: float = 30.0`
- `language: str = "eng"`

## Command Flow

For one page `N`:

1. Create a temp directory.
2. Run renderer:
   - `pdftoppm -f N -l N -r <dpi> -png <source_path> <tmp_prefix>`
3. Find the rendered PNG in the temp directory.
4. Run OCR:
   - `tesseract <image_path> stdout -l <language>`
5. Return stdout text as `OCRPageResult(text=...)`.

`subprocess.run` uses captured stdout/stderr, timeout, and no shell.

## Failure Behavior

- Missing binary -> `RuntimeError("ocr_command_missing:<name>")`.
- Timeout -> `RuntimeError("ocr_command_timeout:<stage>")`.
- Non-zero renderer/OCR exit -> `RuntimeError("ocr_command_failed:<stage>")`.
- No rendered image -> `RuntimeError("ocr_render_missing_output")`.

The existing parser catches provider exceptions when `ocr_strict=false` and records bounded failure reasons; strict mode still raises.

## Config Validate

When `ocr.enabled=true` and provider is `tesseract_cli`, add command availability checks for configured renderer and OCR binaries using `shutil.which`. These are environment checks only; validation does not execute OCR.

## Security / Privacy

- No shell invocation.
- Do not include raw OCR output or stderr in exceptions, logs, config validation detail, or meta.
- Temp files are isolated and removed after each page.

## Compatibility

- Default config is unchanged: OCR disabled and deterministic provider remains default.
- No Python OCR dependencies are added.
- Existing OCR parser behavior and metadata lineage remain unchanged.
