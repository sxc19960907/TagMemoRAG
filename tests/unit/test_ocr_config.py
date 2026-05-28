from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings, load_config


def test_ocr_config_defaults():
    cfg = Settings()

    assert cfg.ocr.enabled is False
    assert cfg.ocr.provider == "deterministic"
    assert cfg.ocr.version == "ocr.v1"
    assert cfg.ocr.trigger == "missing_text"
    assert cfg.ocr.strict_extraction is False


def test_ocr_config_yaml_override(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
ocr:
  enabled: true
  provider: deterministic
  version: test-ocr.v2
  strict_extraction: true
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.ocr.enabled is True
    assert cfg.ocr.provider == "deterministic"
    assert cfg.ocr.version == "test-ocr.v2"
    assert cfg.ocr.strict_extraction is True


def test_ocr_config_tesseract_cli_override(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
ocr:
  enabled: true
  provider: tesseract_cli
  version: tesseract.local.v1
  tesseract_command: /opt/bin/tesseract
  pdf_renderer_command: /opt/bin/pdftoppm
  language: chi_sim+eng
  dpi: 240
  timeout_seconds: 12.5
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.ocr.enabled is True
    assert cfg.ocr.provider == "tesseract_cli"
    assert cfg.ocr.version == "tesseract.local.v1"
    assert cfg.ocr.tesseract_command == "/opt/bin/tesseract"
    assert cfg.ocr.pdf_renderer_command == "/opt/bin/pdftoppm"
    assert cfg.ocr.language == "chi_sim+eng"
    assert cfg.ocr.dpi == 240
    assert cfg.ocr.timeout_seconds == 12.5
