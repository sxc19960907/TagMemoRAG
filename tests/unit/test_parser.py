from __future__ import annotations

from tagmemorag.parser import parse_document


def test_parse_empty_file(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")
    assert parse_document(path) == []


def test_parse_nested_headings(tmp_path):
    path = tmp_path / "manual.md"
    path.write_text("# 产品\n概述内容很多很多很多很多很多。\n## 安装\n连接电源并检查水箱。\n", encoding="utf-8")
    chunks = parse_document(path, min_chars=5)
    assert [chunk.header for chunk in chunks] == ["产品", "安装"]
    assert chunks[1].path == ("产品", "安装")


def test_parse_no_heading(tmp_path):
    path = tmp_path / "plain.txt"
    path.write_text("没有标题的说明书内容。" * 5, encoding="utf-8")
    chunks = parse_document(path, min_chars=5)
    assert len(chunks) == 1
    assert chunks[0].path == ("",)


def test_split_long_blocks(tmp_path):
    path = tmp_path / "long.md"
    path.write_text("# 长段落\n" + ("内容" * 80), encoding="utf-8")
    chunks = parse_document(path, max_chars=80, min_chars=1)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 80 for chunk in chunks)


def test_short_chunks_do_not_merge_across_headings(tmp_path):
    path = tmp_path / "short.md"
    path.write_text("# A\n短内容。\n# B\n短内容。\n", encoding="utf-8")
    chunks = parse_document(path, min_chars=50)
    assert len(chunks) == 2
    assert [chunk.header for chunk in chunks] == ["A", "B"]
