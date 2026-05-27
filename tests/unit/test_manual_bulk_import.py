from __future__ import annotations

from io import BytesIO
import json
import zipfile

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.manual_bulk_import import (
    BulkUploadedFile,
    commit_bulk_import,
    parse_metadata,
    preview_bulk_import,
)
from tagmemorag.manual_library import find_record_by_manual_id, library_root, list_records, load_manifest, upsert_manual


@pytest.fixture
def library_config(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )


def _row(manual_id: str = "cm1", source_file: str = "coffee/cm1.md") -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": "CM1 Manual",
        "source_file": source_file,
        "product_category": "coffee",
        "language": "zh-CN",
        "tags": ["Maintenance Task"],
    }


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


def test_parse_metadata_supports_json_jsonl_and_csv():
    json_rows = parse_metadata(json.dumps([_row()]), "json")
    assert json_rows[0].metadata is not None
    assert json_rows[0].metadata.tags == ("maintenance-task",)

    jsonl_rows = parse_metadata(json.dumps(_row("cm2", "coffee/cm2.txt")) + "\n", "jsonl")
    assert jsonl_rows[0].row == 1
    assert jsonl_rows[0].source_file == "coffee/cm2.txt"

    csv_rows = parse_metadata(
        "manual_id,title,source_file,product_category,language,tags\n"
        "cm3,CM3,coffee/cm3.md,coffee,zh-CN,\"Steam Wand; Deep Clean\"\n",
        "csv",
    )
    assert csv_rows[0].row == 2
    assert csv_rows[0].metadata is not None
    assert csv_rows[0].metadata.tags == ("steam-wand", "deep-clean")


def test_preview_detects_duplicates_unsafe_paths_unsupported_suffix_and_missing_pairs(library_config):
    metadata = json.dumps(
        [
            _row("dup", "coffee/a.md"),
            _row("dup", "coffee/b.md"),
            _row("unsafe", "../escape.md"),
            _row("bad-suffix", "coffee/bad.exe"),
        ]
    )
    preview = preview_bulk_import(
        "default",
        metadata,
        "json",
        [
            BulkUploadedFile("a.md", b"# A\n"),
            BulkUploadedFile("orphan.md", b"# Orphan\n"),
        ],
        library_config,
    )

    codes = {row.code for row in preview.rows}
    assert "DUPLICATE_MANUAL_ID" in codes
    assert "INVALID_INPUT" in codes
    assert "UPLOADED_FILE_WITHOUT_METADATA" in codes
    assert "MISSING_UPLOAD" in codes
    assert preview.error_count >= 4
    assert preview.valid_count == 0


def test_preview_detects_conflicting_status_for_same_target(library_config):
    active = _row("same", "coffee/a.md")
    archived = {**_row("same", "coffee/b.md"), "status": "archived"}

    preview = preview_bulk_import(
        "default",
        json.dumps([active, archived]),
        "json",
        [BulkUploadedFile("a.md", b"# A\n"), BulkUploadedFile("b.md", b"# B\n")],
        library_config,
    )

    assert "CONFLICTING_STATUS" in {row.code for row in preview.rows}


def test_preview_reports_existing_library_conflicts_and_upsert_overwrite_policy(library_config):
    upsert_manual("default", _row(), b"# Existing\n", library_config)

    create_preview = preview_bulk_import(
        "default",
        json.dumps([_row()]),
        "json",
        [BulkUploadedFile("cm1.md", b"# Update\n")],
        library_config,
        mode="create_only",
    )
    assert "EXISTING_MANUAL" in {row.code for row in create_preview.rows}

    blocked_upsert = preview_bulk_import(
        "default",
        json.dumps([_row()]),
        "json",
        [BulkUploadedFile("cm1.md", b"# Update\n")],
        library_config,
        mode="upsert",
    )
    assert "OVERWRITE_REQUIRED" in {row.code for row in blocked_upsert.rows}

    allowed_upsert = preview_bulk_import(
        "default",
        json.dumps([_row()]),
        "json",
        [BulkUploadedFile("cm1.md", b"# Update\n")],
        library_config,
        mode="upsert",
        overwrite=True,
    )
    ready = [row for row in allowed_upsert.rows if row.code == "READY"]
    assert ready[0].action == "update"


def test_preview_maps_metadata_info_hint_without_blocking_row(library_config):
    metadata = {**_row("multi", "coffee/multi.md"), "tags": ["fault-code", "diagnostics", "washer"]}

    preview = preview_bulk_import(
        "default",
        json.dumps([metadata]),
        "json",
        [BulkUploadedFile("multi.md", b"# Multi\n")],
        library_config,
    )

    hints = [row for row in preview.rows if row.code == "TAG_ORDERING_HINT"]
    assert len(hints) == 1
    assert hints[0].severity == "info"
    assert hints[0].action == "skip"
    ready = [row for row in preview.rows if row.code == "READY"]
    assert len(ready) == 1
    assert ready[0].action == "create"
    assert preview.valid_count == 1
    assert preview.error_count == 0


def test_commit_creates_valid_manuals_and_marks_pending(library_config):
    result = commit_bulk_import(
        "default",
        json.dumps([_row(), _row("cm2", "coffee/cm2.txt")]),
        "json",
        [BulkUploadedFile("cm1.md", b"# One\n"), BulkUploadedFile("cm2.txt", b"Two\n")],
        library_config,
    )

    assert result.imported_count == 2
    assert result.failed_count == 0
    assert load_manifest("default", library_config).pending_changes is True
    root = library_root("default", library_config)
    assert (root / "coffee" / "cm1.md").exists()
    assert {record.manual_id for record in list_records("default", library_config)} == {"cm1", "cm2"}


def test_bulk_import_accepts_docx_and_materializes_markdown(library_config):
    result = commit_bulk_import(
        "default",
        json.dumps([_row("docx-guide", "coffee/service-guide.docx")]),
        "json",
        [BulkUploadedFile("service-guide.docx", _docx_bytes("Steam wand pressure", "Clean the nozzle weekly."))],
        library_config,
    )

    assert result.imported_count == 1
    assert result.failed_count == 0
    assert result.preview is not None
    assert result.preview.error_count == 0
    normalized = result.preview.candidates[0]
    assert normalized.source_file == "coffee/service-guide.md"
    assert normalized.uploaded_filename == "service-guide.docx"

    root = library_root("default", library_config)
    source = root / "coffee" / "service-guide.md"
    sidecar = json.loads((root / "coffee" / "service-guide.metadata.json").read_text(encoding="utf-8"))
    assert source.exists()
    assert "Clean the nozzle weekly." in source.read_text(encoding="utf-8")
    assert sidecar["source_file"] == "coffee/service-guide.md"
    assert sidecar["source_format"] == "docx"
    assert sidecar["remote_id"] == "coffee/service-guide.docx"


def test_commit_allows_selected_row_with_metadata_info_hint(library_config):
    metadata = {**_row("multi", "coffee/multi.md"), "tags": ["fault-code", "diagnostics", "washer"]}

    result = commit_bulk_import(
        "default",
        json.dumps([metadata]),
        "json",
        [BulkUploadedFile("multi.md", b"# Multi\n")],
        library_config,
        selected_rows={1},
    )

    assert result.imported_count == 1
    assert result.failed_count == 0
    assert result.preview is not None
    assert result.preview.error_count == 0
    assert find_record_by_manual_id("default", "multi", library_config) is not None


def test_commit_rejects_selected_rows_with_errors(library_config):
    with pytest.raises(ServiceError) as exc:
        commit_bulk_import(
            "default",
            json.dumps([_row("bad", "../escape.md")]),
            "json",
            [],
            library_config,
            selected_rows={1},
        )
    assert exc.value.code == "INVALID_INPUT"
    assert exc.value.detail["rows"] == [1]
