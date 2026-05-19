from __future__ import annotations

from typing import TYPE_CHECKING

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


def create_ocr_provider(settings: "Settings") -> OCRProvider | None:
    cfg = settings.ocr
    if not cfg.enabled:
        return None
    if cfg.provider == "deterministic":
        return DeterministicOCRProvider(version=cfg.version)
    raise ValueError(f"Unsupported OCR provider: {cfg.provider}")


__all__ = ["DeterministicOCRProvider", "create_ocr_provider"]
