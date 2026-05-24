from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import seed_multiformat_real_knowledge as seed  # noqa: E402


HTML = b"""
<!doctype html>
<html>
  <head><title>HTTP caching</title></head>
  <body><main><h1>HTTP caching</h1><p>The no-cache directive forces validation.</p></main></body>
</html>
"""
PDF = b"%PDF-1.4\n% fake enough for materialization unit tests\n"


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


def test_docx_to_markdown_extracts_openxml_text_only():
    markdown = seed._docx_to_markdown(
        _docx_bytes("Purpose: request a waiver.", "Required fields include office and contact."),
        title="EPA Template",
        url="https://example.test/template.docx",
    )

    assert markdown.startswith("# EPA Template")
    assert "Source: https://example.test/template.docx" in markdown
    assert "Purpose: request a waiver." in markdown
    assert "Required fields include office and contact." in markdown


def test_materialize_multiformat_corpus_writes_metadata_and_formats(tmp_path):
    def fake_fetch(url: str, _timeout: float) -> bytes:
        if url.endswith(".pdf"):
            return PDF
        if url.endswith(".docx"):
            return _docx_bytes("Waiver request memo", "Describe why EPA-hosted content is not possible.")
        return HTML

    report = seed.materialize_multiformat_corpus(
        output_dir=tmp_path,
        kb_name="kb",
        fetch_bytes=fake_fetch,
    )

    root = tmp_path / "kb"
    assert report["summary"]["failed"] == 0
    assert (root / "public_web" / "developer.mozilla.org-en-us-docs-web-http-guides-caching.md").exists()
    assert (root / "public_pdf" / "irs-publication-17.pdf").exists()
    docx_markdown = root / "public_docx" / "epa-web-hosting-waiver-memo.md"
    assert "Waiver request memo" in docx_markdown.read_text(encoding="utf-8")

    html_meta = json.loads((root / "public_web" / "developer.mozilla.org-en-us-docs-web-http-guides-caching.metadata.json").read_text(encoding="utf-8"))
    pdf_meta = json.loads((root / "public_pdf" / "irs-publication-17.metadata.json").read_text(encoding="utf-8"))
    docx_meta = json.loads((root / "public_docx" / "epa-web-hosting-waiver-memo.metadata.json").read_text(encoding="utf-8"))

    assert html_meta["source_format"] == "html"
    assert pdf_meta["source_format"] == "pdf"
    assert docx_meta["source_format"] == "docx"
    assert docx_meta["remote_id"].endswith(".docx")


def test_multiformat_sources_cover_html_pdf_and_docx():
    assert {source["source_format"] for source in seed.FILE_SOURCES} == {"pdf", "docx"}
    assert seed.HTML_SOURCES
