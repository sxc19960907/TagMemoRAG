from __future__ import annotations

import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING
from pathlib import Path

from .base import OCRPageContext, OCRPageResult, OCRProvider

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class DeterministicOCRProvider:
    """Fixture-backed OCR provider for tests and local contract validation."""

    provider_name = "deterministic"

    def __init__(self, *, version: str = "ocr.v1"):
        self.version = version

    def recognize_pdf_page(self, context: OCRPageContext) -> OCRPageResult:
        pages = context.metadata.get("ocr_pages") or {}
        if isinstance(pages, dict):
            text = str(pages.get(str(context.page_number)) or pages.get(context.page_number) or "")
        else:
            text = ""
        return OCRPageResult(text=text)


class TesseractCliOCRProvider:
    """Local command-line OCR provider using Poppler pdftoppm and Tesseract."""

    provider_name = "tesseract_cli"

    def __init__(
        self,
        *,
        version: str = "tesseract_cli.v1",
        tesseract_command: str = "tesseract",
        pdf_renderer_command: str = "pdftoppm",
        language: str = "eng",
        dpi: int = 200,
        timeout_seconds: float = 30.0,
    ):
        self.version = version
        self.tesseract_command = tesseract_command
        self.pdf_renderer_command = pdf_renderer_command
        self.language = language
        self.dpi = int(dpi)
        self.timeout_seconds = float(timeout_seconds)

    def recognize_pdf_page(self, context: OCRPageContext) -> OCRPageResult:
        self._ensure_command(self.pdf_renderer_command)
        self._ensure_command(self.tesseract_command)
        with tempfile.TemporaryDirectory(prefix="tagmemorag-ocr-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_prefix = tmp_path / "page"
            page_number = int(context.page_number)
            self._run(
                [
                    self.pdf_renderer_command,
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-r",
                    str(self.dpi),
                    "-png",
                    str(context.source_path),
                    str(output_prefix),
                ],
                stage="render",
            )
            image_path = self._rendered_image(tmp_path)
            ocr = self._run(
                [
                    self.tesseract_command,
                    str(image_path),
                    "stdout",
                    "-l",
                    self.language,
                ],
                stage="ocr",
            )
        return OCRPageResult(text=ocr.stdout.strip())

    def _ensure_command(self, command: str) -> None:
        if shutil.which(command) is None:
            raise RuntimeError(f"ocr_command_missing:{_safe_command_name(command)}")

    def _run(self, command: list[str], *, stage: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                shell=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ocr_command_timeout:{stage}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"ocr_command_failed:{stage}") from exc

    def _rendered_image(self, tmp_path: Path) -> Path:
        images = sorted(tmp_path.glob("*.png"))
        if not images:
            raise RuntimeError("ocr_render_missing_output")
        return images[0]


def _safe_command_name(command: str) -> str:
    return Path(str(command).strip()).name or "unknown"


def create_ocr_provider(settings: "Settings") -> OCRProvider | None:
    cfg = settings.ocr
    if not cfg.enabled:
        return None
    if cfg.provider == "deterministic":
        return DeterministicOCRProvider(version=cfg.version)
    if cfg.provider == "tesseract_cli":
        return TesseractCliOCRProvider(
            version=cfg.version,
            tesseract_command=cfg.tesseract_command,
            pdf_renderer_command=cfg.pdf_renderer_command,
            language=cfg.language,
            dpi=cfg.dpi,
            timeout_seconds=cfg.timeout_seconds,
        )
    raise ValueError(f"Unsupported OCR provider: {cfg.provider}")


__all__ = ["DeterministicOCRProvider", "TesseractCliOCRProvider", "create_ocr_provider"]
