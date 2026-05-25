from __future__ import annotations

import json

from tagmemorag.public_web_import import fetch_public_web_document, html_to_text_blocks, import_public_web


HTML = b"""
<!doctype html>
<html>
  <head><title>Python Tutorial</title><style>.x{}</style></head>
  <body>
    <nav>Skip navigation</nav>
    <p>Outside teaser should not be indexed when main is present.</p>
    <main>
      <h1>Python Tutorial</h1>
      <p>Python is an easy to learn programming language.</p>
      <p>It has efficient high-level data structures.</p>
      <script>ignored()</script>
    </main>
  </body>
</html>
"""


def test_html_to_text_blocks_extracts_title_and_visible_blocks():
    title, blocks = html_to_text_blocks(HTML.decode("utf-8"))

    assert title == "Python Tutorial"
    assert "Python is an easy to learn programming language." in blocks
    assert "Skip navigation" not in " ".join(blocks)
    assert "Outside teaser" not in " ".join(blocks)
    assert "ignored" not in " ".join(blocks)


def test_html_to_text_blocks_falls_back_when_main_is_absent():
    html = """
    <html>
      <head><title>Fallback</title></head>
      <body><article><p>Readable article body.</p></article></body>
    </html>
    """

    title, blocks = html_to_text_blocks(html)

    assert title == "Fallback"
    assert "Readable article body." in blocks


def test_fetch_public_web_document_builds_safe_markdown_record():
    document = fetch_public_web_document(
        "https://docs.python.org/3/tutorial/index.html",
        domain="software_docs",
        doc_type="tutorial",
        tags=("python", "tutorial"),
        fetch_bytes=lambda url, timeout: HTML,
    )

    assert document.title == "Python Tutorial"
    assert document.source_file == "public_web/docs.python.org-3-tutorial-index.html.md"
    assert document.domain == "software_docs"
    assert "Source: https://docs.python.org/3/tutorial/index.html" in document.markdown
    record = document.to_record()
    assert record.manual_id == "docs.python.org-3-tutorial-index.html"
    assert record.product_category == "software_docs"
    assert record.tags == ("python", "tutorial")


def test_import_public_web_preview_does_not_write_files(tmp_path):
    report = import_public_web(
        ("https://docs.python.org/3/tutorial/index.html",),
        output_dir=tmp_path,
        kb_name="general",
        domain="software_docs",
        tags=("python",),
        preview=True,
        fetch_bytes=lambda url, timeout: HTML,
    )

    body = report.to_dict()
    assert body["status"] == "preview"
    assert body["summary"]["parsed"] == 1
    assert not (tmp_path / "general").exists()


def test_import_public_web_materializes_markdown_and_sidecar(tmp_path):
    report = import_public_web(
        ("https://docs.python.org/3/tutorial/index.html",),
        output_dir=tmp_path,
        kb_name="general",
        domain="software_docs",
        doc_type="tutorial",
        tags=("python",),
        fetch_bytes=lambda url, timeout: HTML,
    )

    body = report.to_dict()
    assert body["status"] == "completed"
    assert body["summary"]["materialized"] == 1
    doc = tmp_path / "general" / "public_web" / "docs.python.org-3-tutorial-index.html.md"
    sidecar = tmp_path / "general" / "public_web" / "docs.python.org-3-tutorial-index.html.metadata.json"
    assert "Python is an easy to learn programming language." in doc.read_text(encoding="utf-8")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["manual_id"] == "docs.python.org-3-tutorial-index.html"
    assert metadata["product_category"] == "software_docs"
    assert metadata["domain"] == "software_docs"
    assert metadata["doc_type"] == "tutorial"
    assert metadata["url"] == "https://docs.python.org/3/tutorial/index.html"
    assert metadata["tags"] == ["python"]


def test_import_public_web_reports_invalid_url_without_content():
    report = import_public_web(
        ("file:///etc/passwd",),
        output_dir=None,
        preview=True,
        fetch_bytes=lambda url, timeout: HTML,
    )

    body = report.to_dict()
    assert body["status"] == "preview"
    assert body["summary"]["failed"] == 1
    assert body["failures"] == [{"url": "file:///etc/passwd", "reason": "valueerror"}]


def test_import_public_web_counts_materialize_failures(tmp_path):
    blocked_output = tmp_path / "not-a-directory"
    blocked_output.write_text("x", encoding="utf-8")

    report = import_public_web(
        ("https://docs.python.org/3/tutorial/index.html",),
        output_dir=blocked_output,
        fetch_bytes=lambda url, timeout: HTML,
    )

    body = report.to_dict()
    assert body["status"] == "partial"
    assert body["summary"]["parsed"] == 1
    assert body["summary"]["failed"] == 1
    assert body["summary"]["materialized"] == 0
