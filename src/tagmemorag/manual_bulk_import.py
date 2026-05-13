from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Literal

from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_library import (
    ValidationMessage,
    find_record_by_manual_id,
    list_records,
    metadata_to_dict,
    safe_source_path,
    update_manual_metadata,
    upsert_manual,
    validate_metadata,
)
from .manuals import MANUAL_METADATA_FIELDS, ManualMetadata, normalize_tag
from .parser import SUPPORTED_DOCUMENT_SUFFIXES

BulkImportMode = Literal["create_only", "upsert", "dry_run"]
BulkPreviewAction = Literal["create", "update", "skip", "conflict", "invalid"]
BulkPreviewSeverity = Literal["info", "warning", "error"]

REQUIRED_METADATA_FIELDS = ("manual_id", "title", "source_file", "product_category", "language")
CSV_TAG_SEPARATORS = (",", "\n", ";")


@dataclass(frozen=True)
class BulkUploadedFile:
    filename: str
    content: bytes

    @property
    def normalized_name(self) -> str:
        return _normalize_file_key(self.filename)

    @property
    def basename(self) -> str:
        return Path(self.filename.replace("\\", "/")).name


@dataclass(frozen=True)
class BulkImportCandidate:
    row: int
    manual_id: str
    source_file: str
    metadata: ManualMetadata | None
    raw_metadata: dict[str, Any]
    uploaded_filename: str | None = None
    parse_errors: tuple[ValidationMessage, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "uploaded_filename": self.uploaded_filename,
            "metadata": metadata_to_dict(self.metadata) if self.metadata else None,
            "messages": [message.to_dict() for message in self.parse_errors],
        }


@dataclass(frozen=True)
class BulkPreviewIssue:
    row: int
    manual_id: str | None
    source_file: str | None
    tag: str | None
    status: str | None
    action: BulkPreviewAction
    severity: BulkPreviewSeverity
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "manual_id": self.manual_id or "",
            "source_file": self.source_file or "",
            "tag": self.tag or "",
            "status": self.status or "",
            "action": self.action,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class BulkImportPreview:
    kb_name: str
    mode: BulkImportMode
    valid_count: int
    warning_count: int
    error_count: int
    create_count: int
    update_count: int
    skip_count: int
    rows: tuple[BulkPreviewIssue, ...]
    candidates: tuple[BulkImportCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "mode": self.mode,
            "summary": {
                "valid_count": self.valid_count,
                "warning_count": self.warning_count,
                "error_count": self.error_count,
                "create_count": self.create_count,
                "update_count": self.update_count,
                "skip_count": self.skip_count,
            },
            "rows": [row.to_dict() for row in self.rows],
            "normalized": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class BulkImportResult:
    kb_name: str
    mode: BulkImportMode
    imported_count: int
    skipped_count: int
    failed_count: int
    pending_rebuild: bool
    records: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    preview: BulkImportPreview | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "mode": self.mode,
            "imported_count": self.imported_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "pending_rebuild": self.pending_rebuild,
            "records": list(self.records),
            "failures": list(self.failures),
            "preview": self.preview.to_dict() if self.preview else None,
        }


def parse_metadata(metadata_text: str, metadata_format: str) -> tuple[BulkImportCandidate, ...]:
    fmt = metadata_format.strip().lower()
    if fmt == "json":
        rows = _parse_json_metadata(metadata_text)
    elif fmt == "jsonl":
        rows = _parse_jsonl_metadata(metadata_text)
    elif fmt == "csv":
        rows = _parse_csv_metadata(metadata_text)
    else:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "metadata_format must be json, jsonl, or csv.",
            {"metadata_format": metadata_format},
        )
    return tuple(_candidate_from_raw(row_number, raw) for row_number, raw in rows)


def preview_bulk_import(
    kb_name: str,
    metadata_text: str,
    metadata_format: str,
    uploaded_files: list[BulkUploadedFile],
    cfg: Settings,
    *,
    mode: BulkImportMode = "create_only",
    overwrite: bool = False,
) -> BulkImportPreview:
    _validate_mode(mode)
    candidates = tuple(_match_files(parse_metadata(metadata_text, metadata_format), uploaded_files))
    issues: list[BulkPreviewIssue] = []

    file_by_name = {file.normalized_name: file for file in uploaded_files}
    matched_files = {candidate.uploaded_filename for candidate in candidates if candidate.uploaded_filename}

    for candidate in candidates:
        for message in candidate.parse_errors:
            issues.append(_issue_from_message(candidate, message))
        if candidate.metadata is None:
            continue
        validation = validate_metadata(
            kb_name,
            metadata_to_dict(candidate.metadata) or {},
            cfg,
            mode="upsert" if mode in {"upsert", "dry_run"} else "create",
        )
        for message in validation.messages:
            issues.append(_issue_from_message(candidate, message))
        _append_file_issues(kb_name, candidate, cfg, issues)
        _append_existing_conflicts(kb_name, candidate, cfg, mode=mode, overwrite=overwrite, issues=issues)

    _append_duplicate_issues(candidates, "manual_id", issues)
    _append_duplicate_issues(candidates, "source_file", issues)
    _append_conflicting_status_issues(candidates, issues)
    for uploaded in uploaded_files:
        if uploaded.filename not in matched_files and uploaded.normalized_name not in matched_files:
            issues.append(
                BulkPreviewIssue(
                    row=0,
                    manual_id=None,
                    source_file=uploaded.filename,
                    tag=None,
                    status=None,
                    action="invalid",
                    severity="error",
                    code="UPLOADED_FILE_WITHOUT_METADATA",
                    message="Uploaded document has no matching metadata row.",
                )
            )

    ready_rows = _ready_rows(kb_name, candidates, cfg, mode=mode, issues=issues)
    all_rows = tuple(sorted([*issues, *ready_rows], key=lambda row: (row.row, row.severity, row.code)))
    return _preview_from_rows(kb_name, mode, candidates, all_rows)


def commit_bulk_import(
    kb_name: str,
    metadata_text: str,
    metadata_format: str,
    uploaded_files: list[BulkUploadedFile],
    cfg: Settings,
    *,
    mode: BulkImportMode = "create_only",
    overwrite: bool = False,
    selected_rows: set[int] | None = None,
) -> BulkImportResult:
    preview = preview_bulk_import(
        kb_name,
        metadata_text,
        metadata_format,
        uploaded_files,
        cfg,
        mode=mode,
        overwrite=overwrite,
    )
    if mode == "dry_run":
        return BulkImportResult(
            kb_name=kb_name,
            mode=mode,
            imported_count=0,
            skipped_count=len(preview.candidates),
            failed_count=0,
            pending_rebuild=False,
            preview=preview,
        )
    rows = selected_rows or {candidate.row for candidate in preview.candidates}
    error_rows = {row.row for row in preview.rows if row.severity == "error"}
    selected_error_rows = error_rows & rows
    if selected_error_rows:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Bulk import has selected rows with validation errors.",
            {"rows": sorted(selected_error_rows)},
        )

    uploaded_by_filename = {file.filename: file for file in uploaded_files}
    uploaded_by_key = {file.normalized_name: file for file in uploaded_files}
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    skipped = 0
    for candidate in preview.candidates:
        if candidate.row not in rows:
            skipped += 1
            continue
        if candidate.metadata is None:
            skipped += 1
            continue
        try:
            existing = find_record_by_manual_id(kb_name, candidate.metadata.manual_id, cfg)
            payload = metadata_to_dict(candidate.metadata) or {}
            uploaded = _uploaded_for_candidate(candidate, uploaded_by_filename, uploaded_by_key)
            if uploaded is None and existing is not None and mode == "upsert":
                record = update_manual_metadata(kb_name, candidate.metadata.manual_id, payload, cfg)
            elif uploaded is not None:
                record = upsert_manual(kb_name, payload, uploaded.content, cfg, overwrite=overwrite or mode == "upsert")
            else:
                raise ServiceError(
                    ErrorCode.INVALID_INPUT,
                    "No uploaded source file matched this metadata row.",
                    {"row": candidate.row, "source_file": candidate.source_file},
                )
            records.append(record.to_dict())
        except ServiceError as exc:
            failures.append({"row": candidate.row, "code": exc.code.value, "message": exc.message, "detail": exc.detail})
    return BulkImportResult(
        kb_name=kb_name,
        mode=mode,
        imported_count=len(records),
        skipped_count=skipped,
        failed_count=len(failures),
        pending_rebuild=bool(records),
        records=tuple(records),
        failures=tuple(failures),
        preview=preview,
    )


def _parse_json_metadata(text: str) -> list[tuple[int, dict[str, Any]]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata JSON is not valid.", {"error": str(exc)}) from exc
    if isinstance(parsed, dict) and isinstance(parsed.get("manuals"), list):
        parsed = parsed["manuals"]
    if not isinstance(parsed, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata JSON must be an array or an object with manuals array.")
    rows: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(parsed, 1):
        if not isinstance(item, dict):
            rows.append((index, {"__parse_error__": "metadata row must be an object"}))
        else:
            rows.append((index, dict(item)))
    return rows


def _parse_jsonl_metadata(text: str) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    for index, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append((index, {"__parse_error__": f"metadata JSONL row is not valid JSON: {exc}"}))
            continue
        rows.append((index, dict(parsed) if isinstance(parsed, dict) else {"__parse_error__": "metadata row must be an object"}))
    return rows


def _parse_csv_metadata(text: str) -> list[tuple[int, dict[str, Any]]]:
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata CSV requires a header row.")
    rows: list[tuple[int, dict[str, Any]]] = []
    for index, row in enumerate(reader, 2):
        raw = {str(key): value for key, value in row.items() if key is not None}
        if "tags" in raw:
            raw["tags"] = _parse_csv_tags(str(raw.get("tags") or ""))
        rows.append((index, raw))
    return rows


def _candidate_from_raw(row: int, raw: dict[str, Any]) -> BulkImportCandidate:
    messages: list[ValidationMessage] = []
    if raw.get("__parse_error__"):
        messages.append(ValidationMessage("metadata", "PARSE_ERROR", str(raw["__parse_error__"])))
        return BulkImportCandidate(row=row, manual_id="", source_file="", metadata=None, raw_metadata=raw, parse_errors=tuple(messages))
    unknown = sorted(key for key in raw if key not in MANUAL_METADATA_FIELDS)
    if unknown:
        messages.append(
            ValidationMessage(
                "metadata",
                "UNKNOWN_COLUMN",
                "metadata contains unsupported fields.",
                {"fields": unknown},
            )
        )
    for field_name in REQUIRED_METADATA_FIELDS:
        if not str(raw.get(field_name, "")).strip():
            messages.append(
                ValidationMessage(field_name, "MISSING_REQUIRED_FIELD", f"{field_name} is required.")
            )
    filtered = {key: value for key, value in raw.items() if key in MANUAL_METADATA_FIELDS}
    try:
        metadata = ManualMetadata.from_dict(filtered)
    except ServiceError as exc:
        messages.append(ValidationMessage("metadata", exc.code.value, exc.message, exc.detail))
        metadata = None
    return BulkImportCandidate(
        row=row,
        manual_id=str(raw.get("manual_id", "")).strip(),
        source_file=str(raw.get("source_file", "")).strip(),
        metadata=metadata,
        raw_metadata=dict(raw),
        parse_errors=tuple(messages),
    )


def _match_files(
    candidates: tuple[BulkImportCandidate, ...],
    uploaded_files: list[BulkUploadedFile],
) -> tuple[BulkImportCandidate, ...]:
    matched: list[BulkImportCandidate] = []
    for candidate in candidates:
        if not candidate.source_file:
            matched.append(candidate)
            continue
        matches = _matching_uploads(candidate.source_file, uploaded_files)
        messages = list(candidate.parse_errors)
        uploaded_filename = matches[0].filename if len(matches) == 1 else None
        if len(matches) > 1:
            messages.append(
                ValidationMessage(
                    "source_file",
                    "AMBIGUOUS_FILE_MATCH",
                    "More than one uploaded document matches source_file.",
                    {"source_file": candidate.source_file, "filenames": [file.filename for file in matches]},
                )
            )
        matched.append(
            BulkImportCandidate(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                metadata=candidate.metadata,
                raw_metadata=candidate.raw_metadata,
                uploaded_filename=uploaded_filename,
                parse_errors=tuple(messages),
            )
        )
    return tuple(matched)


def _matching_uploads(source_file: str, uploaded_files: list[BulkUploadedFile]) -> list[BulkUploadedFile]:
    normalized = _normalize_file_key(source_file)
    exact = [file for file in uploaded_files if file.normalized_name == normalized]
    if exact:
        return exact
    basename = Path(source_file.replace("\\", "/")).name
    return [file for file in uploaded_files if file.basename == basename]


def _append_file_issues(
    kb_name: str,
    candidate: BulkImportCandidate,
    cfg: Settings,
    issues: list[BulkPreviewIssue],
) -> None:
    try:
        safe_source_path(kb_name, candidate.source_file, cfg)
    except ServiceError as exc:
        issues.append(_issue_from_message(candidate, ValidationMessage("source_file", exc.code.value, exc.message, exc.detail)))
        return
    suffix = Path(candidate.source_file).suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        issues.append(
            BulkPreviewIssue(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                tag=_first_tag(candidate.metadata),
                status=candidate.metadata.status if candidate.metadata else "",
                action="invalid",
                severity="error",
                code="UNSUPPORTED_SUFFIX",
                message="Unsupported manual document suffix.",
            )
        )


def _append_existing_conflicts(
    kb_name: str,
    candidate: BulkImportCandidate,
    cfg: Settings,
    *,
    mode: BulkImportMode,
    overwrite: bool,
    issues: list[BulkPreviewIssue],
) -> None:
    if candidate.metadata is None:
        return
    existing_by_id = find_record_by_manual_id(kb_name, candidate.metadata.manual_id, cfg)
    existing_by_source = next(
        (record for record in list_records(kb_name, cfg) if record.source_file == candidate.metadata.source_file),
        None,
    )
    existing = existing_by_id or existing_by_source
    if existing is None:
        if not candidate.uploaded_filename:
            issues.append(
                BulkPreviewIssue(
                    row=candidate.row,
                    manual_id=candidate.manual_id,
                    source_file=candidate.source_file,
                    tag=_first_tag(candidate.metadata),
                    status=candidate.metadata.status,
                    action="invalid",
                    severity="error",
                    code="MISSING_UPLOAD",
                    message="No uploaded source file matched this metadata row.",
                )
            )
        return
    if mode == "create_only":
        issues.append(
            BulkPreviewIssue(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                tag=_first_tag(candidate.metadata),
                status=candidate.metadata.status,
                action="conflict",
                severity="error",
                code="EXISTING_MANUAL",
                message="Manual already exists in create-only mode.",
            )
        )
    if existing.status in {"disabled", "archived"} and candidate.metadata.status == "active":
        issues.append(
            BulkPreviewIssue(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                tag=_first_tag(candidate.metadata),
                status=candidate.metadata.status,
                action="conflict",
                severity="error",
                code="REINTRODUCE_INACTIVE_MANUAL",
                message="Disabled or archived manual cannot be reintroduced as active in bulk import.",
            )
        )
    if mode == "upsert" and not overwrite:
        issues.append(
            BulkPreviewIssue(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                tag=_first_tag(candidate.metadata),
                status=candidate.metadata.status,
                action="conflict",
                severity="error",
                code="OVERWRITE_REQUIRED",
                message="Existing manual update requires explicit overwrite approval.",
            )
        )


def _append_duplicate_issues(candidates: tuple[BulkImportCandidate, ...], field_name: str, issues: list[BulkPreviewIssue]) -> None:
    seen: dict[str, list[BulkImportCandidate]] = {}
    for candidate in candidates:
        value = getattr(candidate, field_name)
        if not value:
            continue
        seen.setdefault(value, []).append(candidate)
    code = "DUPLICATE_MANUAL_ID" if field_name == "manual_id" else "DUPLICATE_SOURCE_FILE"
    message = "Duplicate manual_id in this batch." if field_name == "manual_id" else "Duplicate source_file in this batch."
    for group in seen.values():
        if len(group) < 2:
            continue
        for candidate in group:
            issues.append(
                BulkPreviewIssue(
                    row=candidate.row,
                    manual_id=candidate.manual_id,
                    source_file=candidate.source_file,
                    tag=_first_tag(candidate.metadata),
                    status=candidate.metadata.status if candidate.metadata else "",
                    action="conflict",
                    severity="error",
                    code=code,
                    message=message,
                )
            )


def _append_conflicting_status_issues(candidates: tuple[BulkImportCandidate, ...], issues: list[BulkPreviewIssue]) -> None:
    for field_name in ("manual_id", "source_file"):
        grouped: dict[str, list[BulkImportCandidate]] = {}
        for candidate in candidates:
            value = getattr(candidate, field_name)
            if value and candidate.metadata is not None:
                grouped.setdefault(value, []).append(candidate)
        for group in grouped.values():
            statuses = {candidate.metadata.status for candidate in group if candidate.metadata is not None}
            if len(statuses) < 2:
                continue
            for candidate in group:
                issues.append(
                    BulkPreviewIssue(
                        row=candidate.row,
                        manual_id=candidate.manual_id,
                        source_file=candidate.source_file,
                        tag=_first_tag(candidate.metadata),
                        status=candidate.metadata.status if candidate.metadata else "",
                        action="conflict",
                        severity="error",
                        code="CONFLICTING_STATUS",
                        message="Conflicting status values target the same manual_id or source_file.",
                    )
                )


def _ready_rows(
    kb_name: str,
    candidates: tuple[BulkImportCandidate, ...],
    cfg: Settings,
    *,
    mode: BulkImportMode,
    issues: list[BulkPreviewIssue],
) -> list[BulkPreviewIssue]:
    error_rows = {issue.row for issue in issues if issue.severity == "error"}
    ready: list[BulkPreviewIssue] = []
    for candidate in candidates:
        if candidate.row in error_rows or candidate.metadata is None:
            continue
        existing = find_record_by_manual_id(kb_name, candidate.metadata.manual_id, cfg)
        action: BulkPreviewAction = "update" if existing and mode == "upsert" else "create"
        if mode == "dry_run":
            action = "skip"
        ready.append(
            BulkPreviewIssue(
                row=candidate.row,
                manual_id=candidate.manual_id,
                source_file=candidate.source_file,
                tag=_first_tag(candidate.metadata),
                status=candidate.metadata.status,
                action=action,
                severity="info",
                code="READY",
                message="Ready to import." if action != "skip" else "Dry run only; no files will be written.",
            )
        )
    return ready


def _preview_from_rows(
    kb_name: str,
    mode: BulkImportMode,
    candidates: tuple[BulkImportCandidate, ...],
    rows: tuple[BulkPreviewIssue, ...],
) -> BulkImportPreview:
    error_rows = {row.row for row in rows if row.severity == "error"}
    warning_count = sum(1 for row in rows if row.severity == "warning")
    error_count = sum(1 for row in rows if row.severity == "error")
    return BulkImportPreview(
        kb_name=kb_name,
        mode=mode,
        valid_count=sum(1 for candidate in candidates if candidate.row not in error_rows and candidate.metadata is not None),
        warning_count=warning_count,
        error_count=error_count,
        create_count=sum(1 for row in rows if row.code == "READY" and row.action == "create"),
        update_count=sum(1 for row in rows if row.code == "READY" and row.action == "update"),
        skip_count=sum(1 for row in rows if row.code == "READY" and row.action == "skip"),
        rows=rows,
        candidates=candidates,
    )


def _issue_from_message(candidate: BulkImportCandidate, message: ValidationMessage) -> BulkPreviewIssue:
    severity: BulkPreviewSeverity = "warning" if message.code == "UNKNOWN_COLUMN" else "error"
    return BulkPreviewIssue(
        row=candidate.row,
        manual_id=candidate.manual_id,
        source_file=candidate.source_file,
        tag=_first_tag(candidate.metadata),
        status=candidate.metadata.status if candidate.metadata else "",
        action="invalid" if severity == "error" else "skip",
        severity=severity,
        code=message.code,
        message=message.message,
    )


def _uploaded_for_candidate(
    candidate: BulkImportCandidate,
    uploaded_by_filename: dict[str, BulkUploadedFile],
    uploaded_by_key: dict[str, BulkUploadedFile],
) -> BulkUploadedFile | None:
    if not candidate.uploaded_filename:
        return None
    return uploaded_by_filename.get(candidate.uploaded_filename) or uploaded_by_key.get(_normalize_file_key(candidate.uploaded_filename))


def _parse_csv_tags(value: str) -> list[str]:
    tags = [value]
    for separator in CSV_TAG_SEPARATORS:
        split: list[str] = []
        for tag in tags:
            split.extend(tag.split(separator))
        tags = split
    return [normalized for tag in tags if (normalized := normalize_tag(tag))]


def _first_tag(metadata: ManualMetadata | None) -> str:
    if metadata is None or not metadata.tags:
        return ""
    return metadata.tags[0]


def _normalize_file_key(filename: str) -> str:
    return filename.replace("\\", "/").strip().lstrip("./")


def _validate_mode(mode: str) -> None:
    if mode not in {"create_only", "upsert", "dry_run"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be create_only, upsert, or dry_run.", {"mode": mode})
