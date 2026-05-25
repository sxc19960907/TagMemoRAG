from __future__ import annotations

import argparse

from tagmemorag.cli_helpers import add_bulk_args, read_bulk_files, read_text_file, split_csv


def test_split_csv_trims_empty_items():
    assert split_csv(" alpha, ,beta ,, gamma ") == ["alpha", "beta", "gamma"]


def test_read_text_file_uses_utf8(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("蒸汽", encoding="utf-8")

    assert read_text_file(str(path)) == "蒸汽"


def test_read_bulk_files_preserves_filename_and_bytes(tmp_path):
    path = tmp_path / "manual.md"
    path.write_bytes(b"# Manual")

    uploaded = read_bulk_files([str(path)])

    assert len(uploaded) == 1
    assert uploaded[0].filename == "manual.md"
    assert uploaded[0].content == b"# Manual"


def test_add_bulk_args_preserves_import_selected_row_flag():
    parser = argparse.ArgumentParser()
    add_bulk_args(parser, include_import_args=True)

    args = parser.parse_args(["--metadata", "manuals.csv", "--selected-row", "2", "--selected-row", "5"])

    assert args.kb == "default"
    assert args.config == "config.yaml"
    assert args.metadata == "manuals.csv"
    assert args.selected_row == [2, 5]
