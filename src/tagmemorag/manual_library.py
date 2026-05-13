from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from .config import Settings
from .errors import ErrorCode, ServiceError
from .manuals import MANUAL_METADATA_FIELDS, ManualMetadata, metadata_sidecar_path
from .parser import SUPPORTED_DOCUMENT_SUFFIXES
from .storage.atomic import atomic_write
from .types import GraphState

ManualStatus = Literal["active", "disabled", "archived"]

MANIFEST_NAME = ".tagmemorag-library.json"
MANIFEST_SCHEMA_VERSION = "1"
ACTIVE_STATUSES = {"", "active"}
INACTIVE_STATUSES = {"disabled", "archived"}


@dataclass(frozen=True)
class ValidationMessage:
    field: str
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"field": self.field, "code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class ManualLibraryManifest:
    schema_version: str = MANIFEST_SCHEMA_VERSION
    kb_name: str = "default"
    pending_changes: bool = False
    last_successful_build_id: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, kb_name: str) -> "ManualLibraryManifest":
        return cls(
            schema_version=str(data.get("schema_version") or MANIFEST_SCHEMA_VERSION),
            kb_name=str(data.get("kb_name") or kb_name),
            pending_changes=bool(data.get("pending_changes", False)),
            last_successful_build_id=str(data.get("last_successful_build_id") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "pending_changes": self.pending_changes,
            "last_successful_build_id": self.last_successful_build_id,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ManualLibraryRecord:
    kb_name: str
    manual_id: str
    source_file: str
    metadata: ManualMetadata
    status: ManualStatus
    exists: bool
    checksum: str
    updated_at: str
    validation_errors: tuple[ValidationMessage, ...] = ()
    chunk_count: int | None = None
    searchable: bool = False
    rebuild_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "metadata": metadata_to_dict(self.metadata),
            "title": self.metadata.title,
            "brand": self.metadata.brand,
            "product_category": self.metadata.product_category,
            "product_name": self.metadata.product_name,
            "product_model": self.metadata.product_model,
            "language": self.metadata.language,
            "version": self.metadata.version,
            "tags": list(self.metadata.tags),
            "status": self.status,
            "exists": self.exists,
            "checksum": self.checksum,
            "updated_at": self.updated_at,
            "validation_errors": [message.to_dict() for message in self.validation_errors],
            "chunk_count": self.chunk_count,
            "searchable": self.searchable,
            "rebuild_required": self.rebuild_required,
        }


@dataclass(frozen=True)
class MetadataValidationResult:
    valid: bool
    normalized: ManualMetadata | None
    messages: tuple[ValidationMessage, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "normalized": metadata_to_dict(self.normalized) if self.normalized else None,
            "messages": [message.to_dict() for message in self.messages],
        }


def library_root(kb_name: str, cfg: Settings) -> Path:
    root = Path(cfg.manual_library.root_dir).expanduser() / kb_name
    return root.resolve()


def manifest_path(kb_name: str, cfg: Settings) -> Path:
    return library_root(kb_name, cfg) / MANIFEST_NAME


def load_manifest(kb_name: str, cfg: Settings) -> ManualLibraryManifest:
    path = manifest_path(kb_name, cfg)
    if not path.exists():
        return ManualLibraryManifest(kb_name=kb_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Manual library manifest is not valid JSON.",
            {"kb_name": kb_name, "error": str(exc)},
        ) from exc
    return ManualLibraryManifest.from_dict(data, kb_name=kb_name)


def save_manifest(manifest: ManualLibraryManifest, cfg: Settings) -> ManualLibraryManifest:
    updated = replace(manifest, updated_at=_now())
    path = manifest_path(manifest.kb_name, cfg)

    def write(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(path, write)
    return updated


def mark_pending(kb_name: str, cfg: Settings, *, pending: bool = True, build_id: str | None = None) -> ManualLibraryManifest:
    manifest = load_manifest(kb_name, cfg)
    updated = replace(
        manifest,
        pending_changes=pending,
        last_successful_build_id=build_id if build_id is not None else manifest.last_successful_build_id,
    )
    return save_manifest(updated, cfg)


def safe_source_path(kb_name: str, source_file: str, cfg: Settings) -> Path:
    relative = _safe_relative_path(source_file)
    root = library_root(kb_name, cfg)
    target = (root / relative).resolve()
    _ensure_under_root(target, root)
    if target.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Unsupported manual document suffix.",
            {"source_file": source_file, "supported_suffixes": sorted(SUPPORTED_DOCUMENT_SUFFIXES)},
        )
    return target


def validate_metadata(
    kb_name: str,
    data: dict[str, Any],
    cfg: Settings,
    *,
    mode: Literal["create", "update", "upsert"] = "create",
    current_manual_id: str | None = None,
) -> MetadataValidationResult:
    messages: list[ValidationMessage] = []
    try:
        metadata = ManualMetadata.from_dict(data)
    except ServiceError as exc:
        return MetadataValidationResult(
            valid=False,
            normalized=None,
            messages=(ValidationMessage("metadata", exc.code.value, exc.message, exc.detail),),
        )
    try:
        safe_source_path(kb_name, metadata.source_file, cfg)
    except ServiceError as exc:
        messages.append(ValidationMessage("source_file", exc.code.value, exc.message, exc.detail))
    status = metadata.status.lower()
    if status not in ACTIVE_STATUSES | INACTIVE_STATUSES:
        messages.append(
            ValidationMessage(
                "status",
                "INVALID_STATUS",
                "manual status must be active, disabled, or archived.",
                {"status": metadata.status},
            )
        )
    normalized = replace(metadata, status=status or "active")
    duplicate = find_record_by_manual_id(kb_name, normalized.manual_id, cfg)
    if duplicate is not None and mode == "create":
        messages.append(
            ValidationMessage(
                "manual_id",
                "DUPLICATE_MANUAL_ID",
                "manual_id already exists in the target KB.",
                {"manual_id": normalized.manual_id, "source_file": duplicate.source_file},
            )
        )
    elif duplicate is not None and current_manual_id and duplicate.manual_id != current_manual_id:
        messages.append(
            ValidationMessage(
                "manual_id",
                "DUPLICATE_MANUAL_ID",
                "manual_id already exists in the target KB.",
                {"manual_id": normalized.manual_id, "source_file": duplicate.source_file},
            )
        )
    return MetadataValidationResult(valid=not messages, normalized=normalized, messages=tuple(messages))


def upsert_manual(
    kb_name: str,
    metadata_data: dict[str, Any],
    file_bytes: bytes,
    cfg: Settings,
    *,
    overwrite: bool = False,
) -> ManualLibraryRecord:
    validation = validate_metadata(kb_name, metadata_data, cfg, mode="upsert")
    if not validation.valid or validation.normalized is None:
        _raise_validation_error(validation)
    metadata = validation.normalized
    root = library_root(kb_name, cfg)
    source_path = safe_source_path(kb_name, metadata.source_file, cfg)
    sidecar_path = metadata_sidecar_path(source_path)
    duplicate = find_record_by_manual_id(kb_name, metadata.manual_id, cfg)
    if not overwrite and (source_path.exists() or sidecar_path.exists() or duplicate is not None):
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Manual already exists. Set overwrite=true to replace it.",
            {"manual_id": metadata.manual_id, "source_file": metadata.source_file},
        )
    if overwrite and duplicate is not None and duplicate.source_file != metadata.source_file:
        old_path = safe_source_path(kb_name, duplicate.source_file, cfg)
        old_sidecar = metadata_sidecar_path(old_path)
        old_path.unlink(missing_ok=True)
        old_sidecar.unlink(missing_ok=True)
    checksum = hashlib.sha256(file_bytes).hexdigest()
    metadata = replace(metadata, checksum=checksum, uploaded_at=metadata.uploaded_at or _now())
    source_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metadata(sidecar_path, metadata)
    tmp_path = source_path.parent / f".{source_path.name}.upload.tmp"
    try:
        tmp_path.write_bytes(file_bytes)
        os.replace(tmp_path, source_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    mark_pending(kb_name, cfg, pending=True)
    return _record_from_paths(kb_name, root, source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def update_manual_metadata(
    kb_name: str,
    manual_id: str,
    metadata_data: dict[str, Any],
    cfg: Settings,
) -> ManualLibraryRecord:
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    merged = {**metadata_to_dict(existing.metadata), **metadata_data}
    merged["manual_id"] = manual_id
    validation = validate_metadata(kb_name, merged, cfg, mode="update", current_manual_id=manual_id)
    if not validation.valid or validation.normalized is None:
        _raise_validation_error(validation)
    root = library_root(kb_name, cfg)
    old_source = safe_source_path(kb_name, existing.source_file, cfg)
    new_source = safe_source_path(kb_name, validation.normalized.source_file, cfg)
    if old_source != new_source:
        if new_source.exists():
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                "Target source file already exists.",
                {"source_file": validation.normalized.source_file},
            )
        new_source.parent.mkdir(parents=True, exist_ok=True)
        old_source.replace(new_source)
        metadata_sidecar_path(old_source).unlink(missing_ok=True)
    _write_metadata(metadata_sidecar_path(new_source), validation.normalized)
    mark_pending(kb_name, cfg, pending=True)
    return _record_from_paths(kb_name, root, new_source, validation.normalized, load_manifest(kb_name, cfg), graph_state=None)


def replace_manual_file(
    kb_name: str,
    manual_id: str,
    file_bytes: bytes,
    cfg: Settings,
) -> ManualLibraryRecord:
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    source_path = safe_source_path(kb_name, existing.source_file, cfg)
    checksum = hashlib.sha256(file_bytes).hexdigest()
    metadata = replace(existing.metadata, checksum=checksum, uploaded_at=_now())
    tmp_path = source_path.parent / f".{source_path.name}.upload.tmp"
    try:
        tmp_path.write_bytes(file_bytes)
        os.replace(tmp_path, source_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    _write_metadata(metadata_sidecar_path(source_path), metadata)
    mark_pending(kb_name, cfg, pending=True)
    return _record_from_paths(kb_name, library_root(kb_name, cfg), source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def disable_manual(kb_name: str, manual_id: str, cfg: Settings, *, archived: bool = False) -> ManualLibraryRecord:
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    status = "archived" if archived else "disabled"
    metadata = replace(existing.metadata, status=status)
    source_path = safe_source_path(kb_name, existing.source_file, cfg)
    _write_metadata(metadata_sidecar_path(source_path), metadata)
    mark_pending(kb_name, cfg, pending=True)
    return _record_from_paths(kb_name, library_root(kb_name, cfg), source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def delete_manual(kb_name: str, manual_id: str, cfg: Settings) -> dict[str, Any]:
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    source_path = safe_source_path(kb_name, existing.source_file, cfg)
    sidecar_path = metadata_sidecar_path(source_path)
    _ensure_under_root(source_path, library_root(kb_name, cfg))
    _ensure_under_root(sidecar_path, library_root(kb_name, cfg))
    source_path.unlink(missing_ok=True)
    sidecar_path.unlink(missing_ok=True)
    mark_pending(kb_name, cfg, pending=True)
    return {"manual_id": manual_id, "status": "deleted", "rebuild_required": True}


def list_records(kb_name: str, cfg: Settings, *, graph_state: GraphState | None = None) -> list[ManualLibraryRecord]:
    root = library_root(kb_name, cfg)
    manifest = load_manifest(kb_name, cfg)
    if not root.exists():
        return []
    records: list[ManualLibraryRecord] = []
    for sidecar in sorted(root.rglob(f"*{'.metadata.json'}")):
        if sidecar.name == MANIFEST_NAME:
            continue
        data: dict[str, Any] = {}
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata = ManualMetadata.from_dict(data)
            source_path = safe_source_path(kb_name, metadata.source_file, cfg)
            records.append(_record_from_paths(kb_name, root, source_path, metadata, manifest, graph_state=graph_state))
        except ServiceError as exc:
            fallback_source = _fallback_source_for_sidecar(sidecar, root)
            metadata = ManualMetadata(
                manual_id=str(data.get("manual_id", sidecar.stem)),
                title=str(data.get("title", sidecar.stem)),
                source_file=fallback_source,
                product_category=str(data.get("product_category", "unknown")),
            )
            records.append(
                ManualLibraryRecord(
                    kb_name=kb_name,
                    manual_id=metadata.manual_id,
                    source_file=metadata.source_file,
                    metadata=metadata,
                    status="active",
                    exists=False,
                    checksum="",
                    updated_at=_mtime(sidecar),
                    validation_errors=(ValidationMessage("metadata", exc.code.value, exc.message, exc.detail),),
                    rebuild_required=manifest.pending_changes,
                )
            )
    return sorted(records, key=lambda record: record.manual_id)


def find_record_by_manual_id(kb_name: str, manual_id: str, cfg: Settings) -> ManualLibraryRecord | None:
    for record in list_records(kb_name, cfg):
        if record.manual_id == manual_id:
            return record
    return None


def metadata_to_dict(metadata: ManualMetadata | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {field: getattr(metadata, field) if field != "tags" else list(metadata.tags) for field in MANUAL_METADATA_FIELDS}


def is_active_status(status: str) -> bool:
    return status.strip().lower() in ACTIVE_STATUSES


def clear_pending_after_success(kb_name: str, cfg: Settings, build_id: str) -> ManualLibraryManifest:
    return mark_pending(kb_name, cfg, pending=False, build_id=build_id)


def _record_from_paths(
    kb_name: str,
    root: Path,
    source_path: Path,
    metadata: ManualMetadata,
    manifest: ManualLibraryManifest,
    *,
    graph_state: GraphState | None,
) -> ManualLibraryRecord:
    source_path = source_path.resolve()
    status = metadata.status.lower()
    if status not in INACTIVE_STATUSES:
        status = "active"
    chunk_count = None
    searchable = False
    if graph_state is not None:
        count = _chunk_count(graph_state, metadata.manual_id)
        chunk_count = count
        searchable = count > 0
    checksum = metadata.checksum or (_sha256_file(source_path) if source_path.exists() else "")
    return ManualLibraryRecord(
        kb_name=kb_name,
        manual_id=metadata.manual_id,
        source_file=_relative(source_path, root),
        metadata=replace(metadata, source_file=_relative(source_path, root), checksum=checksum),
        status=status,  # type: ignore[arg-type]
        exists=source_path.exists(),
        checksum=checksum,
        updated_at=_mtime(source_path if source_path.exists() else metadata_sidecar_path(source_path)),
        chunk_count=chunk_count,
        searchable=searchable,
        rebuild_required=manifest.pending_changes,
    )


def _safe_relative_path(source_file: str) -> Path:
    value = str(source_file).strip().replace("\\", "/")
    path = Path(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ServiceError(ErrorCode.INVALID_INPUT, "source_file must be a safe relative path.", {"source_file": source_file})
    return path


def _ensure_under_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Path escapes manual library root.", {"path": str(path)}) from exc


def _write_metadata(path: Path, metadata: ManualMetadata) -> None:
    def write(tmp_path: Path) -> None:
        tmp_path.write_text(
            json.dumps(metadata_to_dict(metadata), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    atomic_write(path, write)


def _raise_validation_error(validation: MetadataValidationResult) -> None:
    raise ServiceError(
        ErrorCode.INVALID_INPUT,
        "Manual metadata is not valid.",
        {"messages": [message.to_dict() for message in validation.messages]},
    )


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _mtime(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_count(graph_state: GraphState, manual_id: str) -> int:
    count = 0
    for _, node in graph_state.graph.nodes(data=True):
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else node
        if str(metadata.get("manual_id", "")) == manual_id:
            count += 1
    return count


def _fallback_source_for_sidecar(sidecar: Path, root: Path) -> str:
    stem = sidecar.name[: -len(".metadata.json")]
    for suffix in sorted(SUPPORTED_DOCUMENT_SUFFIXES):
        candidate = sidecar.with_name(stem + suffix)
        if candidate.exists():
            return _relative(candidate, root)
    return _relative(sidecar.with_name(stem + ".md"), root)
