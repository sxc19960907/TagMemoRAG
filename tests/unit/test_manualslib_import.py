from __future__ import annotations

import json

from tagmemorag.manualslib_import import materialize_manualslib_manual, parse_manualslib_page


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
