from __future__ import annotations

import json
import subprocess

from tagmemorag.manualslib_import import materialize_manualslib_manual, parse_manualslib_page
from tagmemorag.manualslib_opencli_import import import_from_opencli


HTML = """
<!doctype html>
<html lang="en">
<head>
  <title>HISENSE DH105M3 SERIES USER'S OPERATION MANUAL Pdf Download | ManualsLib</title>
  <link rel="canonical" href="https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html">
  <script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "url": "https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html",
    "headline": "HISENSE DH105M3 SERIES USER'S OPERATION MANUAL Pdf Download",
    "articleSection": "Hisense Dryer"
  }</script>
  <script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {"@type": "ListItem", "position": 1, "name": "Manuals"},
      {"@type": "ListItem", "position": 2, "name": "Brands"},
      {"@type": "ListItem", "position": 3, "name": "Hisense Manuals"},
      {"@type": "ListItem", "position": 4, "name": "Dryer"},
      {"@type": "ListItem", "position": 5, "name": "DH105M3 Series"},
      {"@type": "ListItem", "position": 6, "name": "User's operation manual"}
    ]
  }</script>
</head>
<body>
<script>
  manual_pages_count = 44;
</script>
<h1>Hisense DH105M3 Series User's Operation Manual</h1>
<a class="mpage active" id="page1" href="/manual/4119276/Hisense-Dh105m3-Series.html#manual" title="Cover">1</a>
<a class="mpage active" id="page28" href="/manual/4119276/Hisense-Dh105m3-Series.html?page=28#manual" title="Programs And Functions">28</a>
<a class="mpage active" id="page43" href="/manual/4119276/Hisense-Dh105m3-Series.html?page=43#manual" title="Waste Disposal">43</a>
<div class="pdf">
  <div style="left:1px;top:1px">Programs and functions</div>
  <div style="left:1px;top:2px">Choose a suitable drying program.</div>
  <div style="left:1px;top:3px">Choose a suitable drying program.</div>
</div>
</body>
</html>
"""


def test_parse_manualslib_page_extracts_metadata_and_pdf_text():
    manual = parse_manualslib_page(
        HTML,
        url="https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html?page=28#manual",
    )

    assert manual.title == "Hisense DH105M3 Series User's Operation Manual"
    assert manual.brand == "Hisense"
    assert manual.product_model == "DH105M3 Series"
    assert manual.product_category == "dryer"
    assert manual.language == "en"
    assert manual.pages_count == 44
    assert manual.pages[0].page_number == 28
    assert manual.pages[0].title == "Programs And Functions"
    assert manual.pages[0].lines == ("Programs and functions", "Choose a suitable drying program.")


def test_materialize_manualslib_manual_writes_markdown_and_sidecar(tmp_path):
    manual = parse_manualslib_page(
        HTML,
        url="https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html?page=28#manual",
    )

    result = materialize_manualslib_manual(manual, output_dir=tmp_path)

    document = tmp_path / "dryer" / "manualslib-hisense-dh105m3-series.md"
    sidecar = tmp_path / "dryer" / "manualslib-hisense-dh105m3-series.metadata.json"
    assert result.document_path == str(document)
    assert document.read_text(encoding="utf-8").startswith("# Hisense DH105M3 Series User's Operation Manual")
    assert "Choose a suitable drying program." in document.read_text(encoding="utf-8")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["manual_id"] == "manualslib-hisense-dh105m3-series"
    assert metadata["source_file"] == "dryer/manualslib-hisense-dh105m3-series.md"
    assert metadata["product_category"] == "dryer"
    assert metadata["product_model"] == "DH105M3 Series"
    assert "manualslib" in metadata["tags"]


def test_import_from_opencli_preview_uses_opencli_json(monkeypatch):
    def fake_run(command, check, text, capture_output):
        assert command == [
            "opencli",
            "manualslib",
            "list",
            "--brand",
            "hisense",
            "--limit",
            "2",
            "-f",
            "json",
            "--category",
            "Dryer",
        ]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {
                        "rank": 1,
                        "brand": "hisense",
                        "category": "Dryer",
                        "model": "DH105M3 Series",
                        "document_type": "User manual",
                        "pages": "44",
                        "url": "https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html",
                    }
                ]
            ),
            stderr="",
        )

    def fail_importer(*args, **kwargs):
        raise AssertionError("preview must not import")

    monkeypatch.setattr("tagmemorag.manualslib_opencli_import.subprocess.run", fake_run)

    report = import_from_opencli(
        brand="hisense",
        category="Dryer",
        limit=2,
        preview=True,
        importer=fail_importer,
    )

    assert report.status == "preview"
    assert report.discovered[0].model == "DH105M3 Series"
    assert report.to_dict()["counts"] == {"discovered": 1, "imported": 0, "skipped": 0, "failed": 0}


def test_import_from_opencli_imports_unique_urls_and_skips_duplicates(monkeypatch, tmp_path):
    url = "https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html"

    def fake_run(command, check, text, capture_output):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                [
                    {"rank": 1, "brand": "hisense", "category": "Dryer", "model": "A", "url": url},
                    {"rank": 2, "brand": "hisense", "category": "Dryer", "model": "A duplicate", "url": url},
                ]
            ),
            stderr="",
        )

    imported_urls = []

    class FakeImportResult:
        def to_dict(self):
            return {
                "document_path": str(tmp_path / "manual.md"),
                "metadata_path": str(tmp_path / "manual.metadata.json"),
                "manual_id": "manualslib-hisense-a",
                "page_count": 1,
                "line_count": 2,
                "source_url": url,
            }

    def fake_importer(import_url, **kwargs):
        imported_urls.append((import_url, kwargs))
        return FakeImportResult()

    monkeypatch.setattr("tagmemorag.manualslib_opencli_import.subprocess.run", fake_run)

    report = import_from_opencli(output_dir=tmp_path, importer=fake_importer)

    assert report.status == "completed"
    assert [item[0] for item in imported_urls] == [url]
    assert imported_urls[0][1]["output_dir"] == tmp_path
    assert report.to_dict()["counts"] == {"discovered": 2, "imported": 1, "skipped": 1, "failed": 0}
    assert report.skipped[0]["reason"] == "duplicate_url"


def test_import_from_opencli_reports_opencli_failure(monkeypatch):
    def fake_run(command, check, text, capture_output):
        return subprocess.CompletedProcess(command, 66, stdout="", stderr="adapter missing")

    monkeypatch.setattr("tagmemorag.manualslib_opencli_import.subprocess.run", fake_run)

    try:
        import_from_opencli(preview=True)
    except Exception as exc:
        assert type(exc).__name__ == "ManualslibOpenCLIError"
        assert "exit code 66" in str(exc)
        assert exc.to_dict()["error"]["stderr"] == "adapter missing"
    else:
        raise AssertionError("expected ManualslibOpenCLIError")
