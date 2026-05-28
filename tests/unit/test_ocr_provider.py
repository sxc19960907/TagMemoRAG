from __future__ import annotations

from pathlib import Path
import subprocess

from tagmemorag.config import OCRConfig, Settings
from tagmemorag.ocr.base import OCRPageContext
from tagmemorag.ocr.provider import DeterministicOCRProvider, TesseractCliOCRProvider, create_ocr_provider


def test_create_ocr_provider_disabled_returns_none():
    assert create_ocr_provider(Settings()) is None


def test_create_ocr_provider_deterministic():
    provider = create_ocr_provider(Settings(ocr=OCRConfig(enabled=True, version="test.v1")))

    assert isinstance(provider, DeterministicOCRProvider)
    assert provider.version == "test.v1"


def test_create_ocr_provider_tesseract_cli():
    provider = create_ocr_provider(
        Settings(
            ocr=OCRConfig(
                enabled=True,
                provider="tesseract_cli",
                version="tess.v1",
                tesseract_command="tess",
                pdf_renderer_command="render",
                language="eng+chi_sim",
                dpi=250,
                timeout_seconds=9,
            )
        )
    )

    assert isinstance(provider, TesseractCliOCRProvider)
    assert provider.version == "tess.v1"
    assert provider.tesseract_command == "tess"
    assert provider.pdf_renderer_command == "render"
    assert provider.language == "eng+chi_sim"
    assert provider.dpi == 250
    assert provider.timeout_seconds == 9


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


def test_tesseract_cli_provider_renders_one_page_and_reads_stdout(monkeypatch, tmp_path):
    calls = []

    def fake_which(command):
        return f"/usr/bin/{command}"

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        if command[0] == "pdftoppm":
            (tmp_path / "page-2.png").write_bytes(b"png")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="Recognized steam label.\n", stderr="")

    monkeypatch.setattr("tagmemorag.ocr.provider.shutil.which", fake_which)
    monkeypatch.setattr("tagmemorag.ocr.provider.tempfile.TemporaryDirectory", lambda prefix: _StaticTempDir(tmp_path))
    monkeypatch.setattr("tagmemorag.ocr.provider.subprocess.run", fake_run)
    provider = TesseractCliOCRProvider(
        version="tess.v1",
        tesseract_command="tesseract",
        pdf_renderer_command="pdftoppm",
        language="eng",
        dpi=220,
        timeout_seconds=7,
    )

    result = provider.recognize_pdf_page(
        OCRPageContext(
            source_path=Path("manual.pdf"),
            source_file="manual.pdf",
            page_number=2,
            kb_name="default",
            doc_id="manual",
        )
    )

    assert result.text == "Recognized steam label."
    assert calls[0][0] == ["pdftoppm", "-f", "2", "-l", "2", "-r", "220", "-png", "manual.pdf", str(tmp_path / "page")]
    assert calls[1][0] == ["tesseract", str(tmp_path / "page-2.png"), "stdout", "-l", "eng"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 7
    assert calls[1][1]["capture_output"] is True


def test_tesseract_cli_provider_missing_command_fails_bounded(monkeypatch):
    monkeypatch.setattr("tagmemorag.ocr.provider.shutil.which", lambda _command: None)
    provider = TesseractCliOCRProvider(pdf_renderer_command="/opt/pdftoppm")

    try:
        provider.recognize_pdf_page(
            OCRPageContext(
                source_path=Path("manual.pdf"),
                source_file="manual.pdf",
                page_number=1,
                kb_name="default",
                doc_id="manual",
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "ocr_command_missing:pdftoppm"
    else:
        raise AssertionError("expected missing command failure")


class _StaticTempDir:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        return str(self.path)

    def __exit__(self, *_exc):
        return False
