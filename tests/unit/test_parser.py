from __future__ import annotations

from tagmemorag.parser import parse_document


class _FakePdfPage:
    def __init__(self, text: str | None):
        self._text = text

    def extract_text(self, *_args, **_kwargs) -> str | None:
        return self._text


class _FakePdfReader:
    def __init__(self, _path: str):
        self.pages = [
            _FakePdfPage("冷藏室温度可以通过控制面板调节。"),
            _FakePdfPage(None),
            _FakePdfPage("若冰箱噪音较大，请检查是否放置平稳。"),
        ]


def test_parse_empty_file(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")
    assert parse_document(path) == []


def test_parse_nested_headings(tmp_path):
    path = tmp_path / "manual.md"
    path.write_text("# 产品\n概述内容很多很多很多很多很多。\n## 安装\n连接电源并检查水箱。\n", encoding="utf-8")
    chunks = parse_document(path, min_chars=5, metadata={"doc_id": "doc-1"})
    assert [chunk.header for chunk in chunks] == ["产品", "安装"]
    assert chunks[1].path == ("产品", "安装")
    assert chunks[1].metadata["doc_id"] == "doc-1"
    assert chunks[1].metadata["section_path"] == ["产品", "安装"]
    assert chunks[1].metadata["asset_refs"] == []
    assert chunks[1].metadata["parser_profile"] == "markdown"
    assert chunks[1].metadata["parser_version"] == "1"
    assert chunks[1].metadata["chunk_id"].startswith("chunk:sha256:")
    assert chunks[1].metadata["element_ids"][0].startswith("element:sha256:")


def test_parse_no_heading(tmp_path):
    path = tmp_path / "plain.txt"
    path.write_text("没有标题的说明书内容。" * 5, encoding="utf-8")
    chunks = parse_document(path, min_chars=5)
    assert len(chunks) == 1
    assert chunks[0].path == ("",)
    assert chunks[0].metadata["section_path"] == []
    assert chunks[0].metadata["parser_profile"] == "txt"
    assert chunks[0].metadata["chunk_id"].startswith("chunk:sha256:")


def test_split_long_blocks(tmp_path):
    path = tmp_path / "long.md"
    path.write_text("# 长段落\n" + ("内容" * 80), encoding="utf-8")
    chunks = parse_document(path, max_chars=80, min_chars=1, metadata={"manual_id": "manual-a"})
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 80 for chunk in chunks)
    assert {chunk.metadata["manual_id"] for chunk in chunks} == {"manual-a"}
    assert {chunk.metadata["doc_id"] for chunk in chunks} == {"manual-a"}
    assert len({chunk.metadata["chunk_id"] for chunk in chunks}) == len(chunks)


def test_split_long_blocks_prefers_english_sentence_boundaries(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(
        "# Procedure\n"
        "Open the service panel and remove the lower filter. "
        "Rinse the filter under running water before reinstalling it. "
        "Close the panel and run a short rinse cycle.\n",
        encoding="utf-8",
    )

    chunks = parse_document(path, max_chars=90, min_chars=1)

    assert len(chunks) == 3
    assert chunks[0].text.endswith("filter.")
    assert chunks[1].text.startswith("Rinse the filter")
    assert chunks[2].text.startswith("Close the panel")
    assert all(len(chunk.text) <= 90 for chunk in chunks)
    assert {chunk.metadata["split_reason"] for chunk in chunks} == {"sentence_boundary"}


def test_split_long_blocks_prefers_cjk_sentence_boundaries(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(
        "# 操作\n打开检修盖并取出过滤器。用清水冲洗过滤器后再装回。关闭检修盖并运行短程序。\n",
        encoding="utf-8",
    )

    chunks = parse_document(path, max_chars=24, min_chars=1)

    assert [chunk.text for chunk in chunks] == [
        "操作\n打开检修盖并取出过滤器。",
        "用清水冲洗过滤器后再装回。",
        "关闭检修盖并运行短程序。",
    ]


def test_split_long_blocks_falls_back_for_unpunctuated_text(tmp_path):
    path = tmp_path / "long.md"
    path.write_text("# Data\n" + ("abcdefghijklmnopqrstuvwxyz" * 4), encoding="utf-8")

    chunks = parse_document(path, max_chars=40, min_chars=1)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 40 for chunk in chunks)


def test_overlap_applies_to_split_siblings_without_duplicate_chunk_ids(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(
        "# Procedure\n"
        "Open the service panel and remove the lower filter. "
        "Rinse the filter under running water before reinstalling it. "
        "Close the panel and run a short rinse cycle.\n",
        encoding="utf-8",
    )

    chunks = parse_document(path, max_chars=90, min_chars=1, overlap_chars=24)

    assert len(chunks) == 3
    assert chunks[1].text.startswith("remove the lower filter.")
    assert len({chunk.metadata["chunk_id"] for chunk in chunks}) == len(chunks)


def test_markdown_table_splits_on_rows_and_repeats_header(tmp_path):
    path = tmp_path / "table.md"
    path.write_text(
        "# Faults\n"
        "| Code | Meaning | Action |\n"
        "| --- | --- | --- |\n"
        "| E01 | Door is open | Close the door and restart. |\n"
        "| E02 | Filter is blocked | Remove the lower filter and rinse it. |\n"
        "| E03 | Water tank full | Empty the tank before continuing. |\n",
        encoding="utf-8",
    )

    chunks = parse_document(path, max_chars=120, min_chars=1)

    table_chunks = [chunk for chunk in chunks if chunk.metadata.get("chunk_kind") == "table"]

    assert len(table_chunks) >= 2
    assert all("| Code | Meaning | Action |" in chunk.text for chunk in table_chunks)
    assert any("E02" in chunk.text for chunk in chunks)
    assert {chunk.metadata["split_reason"] for chunk in table_chunks} == {"table_row_boundary"}


def test_short_chunks_do_not_merge_across_headings(tmp_path):
    path = tmp_path / "short.md"
    path.write_text("# A\n短内容。\n# B\n短内容。\n", encoding="utf-8")
    chunks = parse_document(path, min_chars=50)
    assert len(chunks) == 2
    assert [chunk.header for chunk in chunks] == ["A", "B"]


def test_parse_pdf_pages(monkeypatch, tmp_path):
    monkeypatch.setattr("tagmemorag.parser.PdfReader", _FakePdfReader)
    path = tmp_path / "fridge.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, min_chars=1, metadata={"manual_id": "fridge", "tags": ["temperature-setting"]})

    assert len(chunks) == 2
    assert [chunk.header for chunk in chunks] == ["Page 1", "Page 3"]
    assert chunks[0].path == ("Page 1",)
    assert chunks[0].source_file == "fridge.pdf"
    assert chunks[0].metadata["manual_id"] == "fridge"
    assert chunks[0].metadata["page_start"] == 1
    assert chunks[0].metadata["page_end"] == 1
    assert chunks[0].metadata["pdf_header_source"] == "page_fallback"
    assert chunks[0].metadata["pdf_parser_profile"] == "product_manual"
    assert chunks[0].metadata["parser_profile"] == "pdf:product_manual"
    assert chunks[0].metadata["parser_version"] == "1"
    assert chunks[0].metadata["doc_id"] == "fridge"
    assert chunks[0].metadata["section_path"] == ["Page 1"]
    assert chunks[0].metadata["asset_refs"] == []
    assert chunks[0].metadata["chunk_id"].startswith("chunk:sha256:")
    assert "冷藏室温度" in chunks[0].text


def test_parse_pdf_detects_section_headings(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [
                _FakePdfPage(
                    "Safety\n"
                    "Do not let children play with the appliance.\n"
                    "Operation\n"
                    "Select the drying program and press Start.\n"
                )
            ]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    path = tmp_path / "dryer.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, min_chars=1, metadata={"manual_id": "dryer"})

    assert [chunk.header for chunk in chunks] == ["Safety", "Operation"]
    assert [chunk.path for chunk in chunks] == [("Safety",), ("Operation",)]
    assert {chunk.metadata["pdf_header_source"] for chunk in chunks} == {"detected"}
    assert {chunk.metadata["pdf_parser_profile"] for chunk in chunks} == {"product_manual"}
    assert {chunk.metadata["page_start"] for chunk in chunks} == {1}
    assert "press Start" in chunks[1].text


def test_parse_pdf_generic_profile_uses_structural_headings_without_product_manual_hints(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [
                _FakePdfPage(
                    "1. Engine Diagnostics\n"
                    "Check compression and ignition timing before replacing parts.\n"
                    "2. Brake Service\n"
                    "Inspect pads and hydraulic lines.\n"
                )
            ]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    path = tmp_path / "vehicle.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, min_chars=1, pdf_profile="generic")

    assert [chunk.header for chunk in chunks] == ["1. Engine Diagnostics", "2. Brake Service"]
    assert {chunk.metadata["pdf_header_source"] for chunk in chunks} == {"detected"}
    assert {chunk.metadata["pdf_parser_profile"] for chunk in chunks} == {"generic"}


def test_parse_pdf_generic_profile_ignores_product_manual_heading_hints(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [
                _FakePdfPage(
                    "troubleshooting\n"
                    "Use this section only when the device reports an error.\n"
                )
            ]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    path = tmp_path / "generic.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, min_chars=1, pdf_profile="generic")

    assert [chunk.header for chunk in chunks] == ["Page 1"]
    assert chunks[0].metadata["pdf_header_source"] == "page_fallback"


def test_parse_pdf_custom_heading_hints_extend_generic_profile(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [
                _FakePdfPage(
                    "troubleshooting\n"
                    "Use this section only when the device reports an error.\n"
                )
            ]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    path = tmp_path / "generic.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, min_chars=1, pdf_profile="generic", pdf_heading_hints=["troubleshooting"])

    assert [chunk.header for chunk in chunks] == ["troubleshooting"]
    assert chunks[0].metadata["pdf_header_source"] == "detected"


def test_parse_pdf_preserves_page_metadata_when_splitting(monkeypatch, tmp_path):
    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [_FakePdfPage("Troubleshooting\n" + ("Noise problem. " * 30))]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    path = tmp_path / "fridge.pdf"
    path.write_bytes(b"%PDF fake")

    chunks = parse_document(path, max_chars=80, min_chars=1, metadata={"manual_id": "fridge"})

    assert len(chunks) > 1
    assert {chunk.header for chunk in chunks} == {"Troubleshooting"}
    assert all(chunk.metadata["page_start"] == 1 for chunk in chunks)
    assert all(chunk.metadata["page_end"] == 1 for chunk in chunks)
    assert all(chunk.metadata["pdf_header_source"] == "detected" for chunk in chunks)
    assert len({chunk.metadata["chunk_id"] for chunk in chunks}) == len(chunks)


def test_chunk_id_is_deterministic_for_same_content(tmp_path):
    path = tmp_path / "manual.md"
    path.write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")

    first = parse_document(path, min_chars=1, root_dir=tmp_path, metadata={"manual_id": "coffee"})
    second = parse_document(path, min_chars=1, root_dir=tmp_path, metadata={"manual_id": "coffee"})

    assert [chunk.metadata["chunk_id"] for chunk in first] == [chunk.metadata["chunk_id"] for chunk in second]
    assert [chunk.metadata["element_ids"] for chunk in first] == [chunk.metadata["element_ids"] for chunk in second]


def test_chunk_id_changes_when_text_changes(tmp_path):
    path = tmp_path / "manual.md"
    path.write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    original = parse_document(path, min_chars=1, root_dir=tmp_path, metadata={"manual_id": "coffee"})[0]

    path.write_text("# 操作\n蒸汽功能可以制作热奶泡。\n", encoding="utf-8")
    changed = parse_document(path, min_chars=1, root_dir=tmp_path, metadata={"manual_id": "coffee"})[0]

    assert changed.metadata["chunk_id"] != original.metadata["chunk_id"]
