from __future__ import annotations

from pathlib import Path

from tagmemorag.config import OCRConfig, Settings
from tagmemorag.ocr.base import OCRPageContext
from tagmemorag.ocr.provider import DeterministicOCRProvider, create_ocr_provider


def test_create_ocr_provider_disabled_returns_none():
    assert create_ocr_provider(Settings()) is None


def test_create_ocr_provider_deterministic():
    provider = create_ocr_provider(Settings(ocr=OCRConfig(enabled=True, version="test.v1")))

    assert isinstance(provider, DeterministicOCRProvider)
    assert provider.version == "test.v1"


def test_deterministic_ocr_provider_reads_fixture_text():
    provider = DeterministicOCRProvider(version="test.v1")
    context = OCRPageContext(
        source_path=Path("manual.pdf"),
        source_file="manual.pdf",
        page_number=2,
        kb_name="default",
        doc_id="manual",
        metadata={"ocr_pages": {"2": "OCR recognized steam label."}},
    )

    result = provider.recognize_pdf_page(context)

    assert result.text == "OCR recognized steam label."
