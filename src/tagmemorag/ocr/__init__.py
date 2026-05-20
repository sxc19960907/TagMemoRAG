"""OCR text ingestion boundary for scanned PDF pages (T7)."""

from .base import OCRPageContext, OCRPageResult, OCRProvider, OCRSummary
from .provider import DeterministicOCRProvider, create_ocr_provider

__all__ = [
    "DeterministicOCRProvider",
    "OCRPageContext",
    "OCRPageResult",
    "OCRProvider",
    "OCRSummary",
    "create_ocr_provider",
]
