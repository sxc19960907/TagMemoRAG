from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

from .config import Settings
from .epa_basis import mark_epa_basis_dirty
from .errors import ErrorCode, ServiceError
from .manual_blob_store import BlobRef, create_blob_store, guess_content_type
from .manual_registry import ManualRecord, RegistryMigrationReport, create_registry
from .manuals import MANUAL_METADATA_FIELDS, ManualMetadata, metadata_sidecar_path
from .parser_provider import supported_document_suffixes
from .storage.atomic import atomic_write
from .tag_store import delete_manual_tags, delete_tags, find_orphan_tags
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
class DirtyManual:
    manual_id: str
    source_file: str = ""
    operation: str = "upsert"
    updated_at: str = ""
    checksum: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, manual_id: str) -> "DirtyManual":
        return cls(
            manual_id=str(data.get("manual_id") or manual_id),
            source_file=str(data.get("source_file") or ""),
            operation=str(data.get("operation") or "upsert"),
            updated_at=str(data.get("updated_at") or ""),
            checksum=str(data.get("checksum") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "operation": self.operation,
            "updated_at": self.updated_at,
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class ManualLibraryManifest:
    schema_version: str = MANIFEST_SCHEMA_VERSION
    kb_name: str = "default"
    pending_changes: bool = False
    last_successful_build_id: str = ""
    updated_at: str = ""
    dirty_manuals: dict[str, DirtyManual] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, kb_name: str) -> "ManualLibraryManifest":
        dirty_data = data.get("dirty_manuals")
        dirty_manuals: dict[str, DirtyManual] = {}
        if isinstance(dirty_data, dict):
            for key, value in dirty_data.items():
                if isinstance(value, dict):
                    dirty = DirtyManual.from_dict(value, manual_id=str(key))
                    dirty_manuals[dirty.manual_id] = dirty
        return cls(
            schema_version=str(data.get("schema_version") or MANIFEST_SCHEMA_VERSION),
            kb_name=str(data.get("kb_name") or kb_name),
            pending_changes=bool(data.get("pending_changes", False)),
            last_successful_build_id=str(data.get("last_successful_build_id") or ""),
            updated_at=str(data.get("updated_at") or ""),
            dirty_manuals=dirty_manuals,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "pending_changes": self.pending_changes,
            "last_successful_build_id": self.last_successful_build_id,
            "updated_at": self.updated_at,
            "dirty_manuals": {key: value.to_dict() for key, value in sorted(self.dirty_manuals.items())},
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
    storage_backend: str = ""
    blob_key: str = ""
    size_bytes: int = 0
    content_type: str = ""
    registry_backend: str = "file"
    registry_version: int = 0

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
            "storage_backend": self.storage_backend,
            "blob_key": self.blob_key,
            "blob_ref_present": bool(self.blob_key),
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "registry_backend": self.registry_backend,
            "registry_version": self.registry_version,
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


def registry_enabled(cfg: Settings) -> bool:
    return cfg.manual_library.registry_backend == "sqlite"


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


def mark_pending(
    kb_name: str,
    cfg: Settings,
    *,
    pending: bool = True,
    build_id: str | None = None,
    dirty: DirtyManual | dict[str, Any] | None = None,
) -> ManualLibraryManifest:
    manifest = load_manifest(kb_name, cfg)
    dirty_manuals = dict(manifest.dirty_manuals)
    if dirty is not None:
        dirty_obj = dirty if isinstance(dirty, DirtyManual) else DirtyManual.from_dict(dirty, manual_id=str(dirty.get("manual_id", "")))
        dirty_manuals[dirty_obj.manual_id] = replace(dirty_obj, updated_at=dirty_obj.updated_at or _now())
    if not pending:
        dirty_manuals = {}
    updated = replace(
        manifest,
        pending_changes=pending,
        last_successful_build_id=build_id if build_id is not None else manifest.last_successful_build_id,
        dirty_manuals=dirty_manuals,
    )
    return save_manifest(updated, cfg)


def mark_dirty(
    kb_name: str,
    cfg: Settings,
    *,
    manual_id: str,
    source_file: str = "",
    operation: str,
    checksum: str = "",
) -> ManualLibraryManifest:
    return mark_pending(
        kb_name,
        cfg,
        pending=True,
        dirty=DirtyManual(
            manual_id=manual_id,
            source_file=source_file,
            operation=operation,
            updated_at=_now(),
            checksum=checksum,
        ),
    )


def safe_source_path(kb_name: str, source_file: str, cfg: Settings) -> Path:
    relative = _safe_relative_path(source_file)
    root = library_root(kb_name, cfg)
    target = (root / relative).resolve()
    _ensure_under_root(target, root)
    suffixes = supported_document_suffixes(cfg.parser)
    if target.suffix.lower() not in suffixes:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Unsupported manual document suffix.",
            {"source_file": source_file, "supported_suffixes": sorted(suffixes)},
        )
    return target


def validate_metadata(
    kb_name: str,
    data: dict[str, Any],
    cfg: Settings,
    *,
    mode: Literal["create", "update", "upsert"] = "create",
    current_manual_id: str | None = None,
    tag_policy: Any | None = None,
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
    if tag_policy is not None:
        from .tag_governance import governance_validation_messages

        messages.extend(governance_validation_messages(normalized.tags, tag_policy))
    if len(normalized.tags) >= 2:
        messages.append(
            ValidationMessage(
                "tags",
                "TAG_ORDERING_HINT",
                "tags array order is read by future search re-ranking; order from specific to broad (see docs/tag-ordering-convention.md).",
                {"tags": list(normalized.tags), "severity": "info"},
            )
        )
    blocking_messages = [message for message in messages if message.detail.get("severity") not in {"warning", "info"}]
    return MetadataValidationResult(valid=not blocking_messages, normalized=normalized, messages=tuple(messages))


def upsert_manual(
    kb_name: str,
    metadata_data: dict[str, Any],
    file_bytes: bytes,
    cfg: Settings,
    *,
    overwrite: bool = False,
) -> ManualLibraryRecord:
    if registry_enabled(cfg):
        return _upsert_manual_registry(kb_name, metadata_data, file_bytes, cfg, overwrite=overwrite)
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
    mark_dirty(
        kb_name,
        cfg,
        manual_id=metadata.manual_id,
        source_file=metadata.source_file,
        operation="upsert",
        checksum=checksum,
    )
    return _record_from_paths(kb_name, root, source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def update_manual_metadata(
    kb_name: str,
    manual_id: str,
    metadata_data: dict[str, Any],
    cfg: Settings,
) -> ManualLibraryRecord:
    if registry_enabled(cfg):
        return _update_manual_metadata_registry(kb_name, manual_id, metadata_data, cfg)
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
    mark_dirty(
        kb_name,
        cfg,
        manual_id=manual_id,
        source_file=validation.normalized.source_file,
        operation="metadata_update",
        checksum=validation.normalized.checksum,
    )
    return _record_from_paths(kb_name, root, new_source, validation.normalized, load_manifest(kb_name, cfg), graph_state=None)


def replace_manual_file(
    kb_name: str,
    manual_id: str,
    file_bytes: bytes,
    cfg: Settings,
) -> ManualLibraryRecord:
    if registry_enabled(cfg):
        return _replace_manual_file_registry(kb_name, manual_id, file_bytes, cfg)
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
    mark_dirty(
        kb_name,
        cfg,
        manual_id=manual_id,
        source_file=existing.source_file,
        operation="file_replace",
        checksum=checksum,
    )
    return _record_from_paths(kb_name, library_root(kb_name, cfg), source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def disable_manual(kb_name: str, manual_id: str, cfg: Settings, *, archived: bool = False) -> ManualLibraryRecord:
    if registry_enabled(cfg):
        return _disable_manual_registry(kb_name, manual_id, cfg, archived=archived)
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    status = "archived" if archived else "disabled"
    metadata = replace(existing.metadata, status=status)
    source_path = safe_source_path(kb_name, existing.source_file, cfg)
    _write_metadata(metadata_sidecar_path(source_path), metadata)
    mark_dirty(
        kb_name,
        cfg,
        manual_id=manual_id,
        source_file=existing.source_file,
        operation="archive" if archived else "disable",
        checksum=metadata.checksum,
    )
    return _record_from_paths(kb_name, library_root(kb_name, cfg), source_path, metadata, load_manifest(kb_name, cfg), graph_state=None)


def delete_manual(kb_name: str, manual_id: str, cfg: Settings) -> dict[str, Any]:
    if registry_enabled(cfg):
        return _delete_manual_registry(kb_name, manual_id, cfg)
    existing = find_record_by_manual_id(kb_name, manual_id, cfg)
    if existing is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    source_path = safe_source_path(kb_name, existing.source_file, cfg)
    sidecar_path = metadata_sidecar_path(source_path)
    _ensure_under_root(source_path, library_root(kb_name, cfg))
    _ensure_under_root(sidecar_path, library_root(kb_name, cfg))
    source_path.unlink(missing_ok=True)
    sidecar_path.unlink(missing_ok=True)
    mark_dirty(kb_name, cfg, manual_id=manual_id, source_file=existing.source_file, operation="hard_delete", checksum=existing.checksum)
    orphan_tags_removed = _cleanup_deleted_manual_tags(kb_name, manual_id, cfg)
    return {
        "manual_id": manual_id,
        "status": "deleted",
        "rebuild_required": True,
        "orphan_tags_removed": orphan_tags_removed,
    }


def list_records(kb_name: str, cfg: Settings, *, graph_state: GraphState | None = None) -> list[ManualLibraryRecord]:
    if registry_enabled(cfg):
        return _list_records_registry(kb_name, cfg, graph_state=graph_state)
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


def migrate_sidecars_to_registry(kb_name: str, cfg: Settings, *, dry_run: bool = True) -> RegistryMigrationReport:
    if not registry_enabled(cfg):
        raise ServiceError(ErrorCode.INVALID_CONFIG, "manual_library.registry_backend must be sqlite for registry migration.")
    root = library_root(kb_name, cfg)
    registry = create_registry(cfg.manual_library.registry_path)
    blob_store = create_blob_store(cfg)
    imported = skipped = invalid = missing = duplicates = 0
    seen_manual_ids: set[str] = set()
    if not root.exists():
        return RegistryMigrationReport(kb_name=kb_name, dry_run=dry_run)
    for sidecar in sorted(root.rglob("*.metadata.json")):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata = ManualMetadata.from_dict(data)
            source_path = safe_source_path(kb_name, metadata.source_file, cfg)
        except (OSError, json.JSONDecodeError, ServiceError):
            invalid += 1
            continue
        if metadata.manual_id in seen_manual_ids:
            duplicates += 1
            continue
        seen_manual_ids.add(metadata.manual_id)
        if registry.get(kb_name, metadata.manual_id) is not None:
            skipped += 1
            continue
        if not source_path.exists():
            missing += 1
            continue
        content = source_path.read_bytes()
        if dry_run:
            imported += 1
            continue
        checksum = hashlib.sha256(content).hexdigest()
        metadata = replace(metadata, checksum=metadata.checksum or checksum, uploaded_at=metadata.uploaded_at or _now())
        blob_ref = blob_store.put(
            kb_name,
            metadata.manual_id,
            metadata.source_file,
            content,
            {"content_type": guess_content_type(metadata.source_file), "version": 1},
        )
        registry.upsert(kb_name, metadata, blob_ref, operation="migrate")
        imported += 1
    return RegistryMigrationReport(
        kb_name=kb_name,
        dry_run=dry_run,
        imported_records=imported,
        skipped_records=skipped,
        invalid_metadata=invalid,
        missing_files=missing,
        duplicate_manual_ids=duplicates,
    )


def verify_registry_blobs(kb_name: str, cfg: Settings) -> dict[str, Any]:
    if not registry_enabled(cfg):
        raise ServiceError(ErrorCode.INVALID_CONFIG, "manual_library.registry_backend must be sqlite to verify registry blobs.")
    registry = create_registry(cfg.manual_library.registry_path)
    blob_store = create_blob_store(cfg)
    missing: list[dict[str, str]] = []
    for record in registry.list(kb_name):
        if record.blob_backend != blob_store.backend or not blob_store.exists(record.blob_key):
            missing.append({"manual_id": record.manual_id, "blob_key": record.blob_key, "blob_backend": record.blob_backend})
    return {"kb_name": kb_name, "checked_count": len(registry.list(kb_name)), "missing_count": len(missing), "missing": missing}


def registry_inspect(kb_name: str, cfg: Settings) -> dict[str, Any]:
    backend = cfg.manual_library.registry_backend
    if backend != "sqlite":
        return {"kb_name": kb_name, "registry_backend": backend, "enabled": False}
    registry = create_registry(cfg.manual_library.registry_path)
    records = registry.list(kb_name, include_deleted=True)
    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
    return {
        "kb_name": kb_name,
        "registry_backend": backend,
        "enabled": True,
        "registry_path": str(Path(cfg.manual_library.registry_path).expanduser()),
        "record_count": len(records),
        "status_counts": status_counts,
        "blob_backend": cfg.manual_library.blob_backend,
    }


@contextmanager
def materialize_registry_build_source(kb_name: str, cfg: Settings):
    if not registry_enabled(cfg):
        raise ServiceError(ErrorCode.INVALID_CONFIG, "manual registry is not enabled.")
    staging_root = Path(tempfile.mkdtemp(prefix=f"tagmemorag-{kb_name}-registry-"))
    try:
        registry = create_registry(cfg.manual_library.registry_path)
        blob_store = create_blob_store(cfg)
        for record in registry.list(kb_name):
            if not is_active_status(record.status):
                continue
            source_path = (staging_root / _safe_relative_path(record.source_file)).resolve()
            _ensure_under_root(source_path, staging_root)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(blob_store.get(record.blob_key))
            _write_metadata(metadata_sidecar_path(source_path), record.metadata)
        yield staging_root
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def metadata_to_dict(metadata: ManualMetadata | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {field: getattr(metadata, field) if field != "tags" else list(metadata.tags) for field in MANUAL_METADATA_FIELDS}


def is_active_status(status: str) -> bool:
    return status.strip().lower() in ACTIVE_STATUSES


def clear_pending_after_success(kb_name: str, cfg: Settings, build_id: str) -> ManualLibraryManifest:
    return mark_pending(kb_name, cfg, pending=False, build_id=build_id)


def build_rebuild_operations_summary(
    *,
    kb_name: str,
    cfg: Settings,
    task: Any | None = None,
    graph_state: GraphState | None = None,
    manifest: ManualLibraryManifest | None = None,
) -> dict[str, Any]:
    manifest = manifest if manifest is not None else load_manifest(kb_name, cfg)
    current_build_id = graph_state.build_id if graph_state is not None else ""
    qdrant_sync = _low_cardinality_qdrant_sync(
        getattr(task, "qdrant_sync", None) if task is not None else _meta_dict(graph_state).get("qdrant_sync")
    )
    fallback_reason = str(getattr(task, "fallback_reason", "") or "")
    chunk_identity_fallback_reason = str(getattr(task, "chunk_identity_fallback_reason", "") or "")
    summary = {
        "task_id": str(getattr(task, "task_id", "") or ""),
        "status": str(getattr(task, "status", "") or ""),
        "requested_mode": str(getattr(task, "requested_mode", "") or ""),
        "effective_mode": str(getattr(task, "effective_mode", "") or ""),
        "fallback_reason": fallback_reason,
        "auto_decision_reason": str(getattr(task, "auto_decision_reason", "") or ""),
        "dirty_manual_count": int(getattr(task, "dirty_manual_count", len(manifest.dirty_manuals)) or 0),
        "reused_chunk_count": int(getattr(task, "reused_chunk_count", 0) or 0),
        "embedded_chunk_count": int(getattr(task, "embedded_chunk_count", 0) or 0),
        "chunk_identity_fallback_reason": chunk_identity_fallback_reason,
        "qdrant_sync": qdrant_sync,
        "current_build_id": current_build_id,
        "last_successful_build_id": manifest.last_successful_build_id or current_build_id,
        "pending_changes": manifest.pending_changes,
    }
    summary["recovery_hint"] = _primary_recovery_hint(
        status=summary["status"],
        pending_changes=manifest.pending_changes,
        provider=cfg.vector_store.provider,
        qdrant_sync=qdrant_sync,
        fallback_reason=fallback_reason,
        chunk_identity_fallback_reason=chunk_identity_fallback_reason,
    )
    return summary


def build_dirty_state_report(kb_name: str, cfg: Settings, *, graph_state: GraphState | None = None) -> dict[str, Any]:
    manifest = load_manifest(kb_name, cfg)
    last_impact = _load_last_impact_summary(kb_name, cfg)
    last_qdrant_sync = _low_cardinality_qdrant_sync(
        last_impact.get("qdrant_sync") if last_impact else _meta_dict(graph_state).get("qdrant_sync")
    )
    return {
        "kb_name": kb_name,
        "pending_changes": manifest.pending_changes,
        "dirty_manual_count": len(manifest.dirty_manuals),
        "dirty_manuals": export_dirty_state(kb_name, cfg, graph_state=graph_state),
        "current_build_id": graph_state.build_id if graph_state is not None else "",
        "last_successful_build_id": manifest.last_successful_build_id or (graph_state.build_id if graph_state is not None else ""),
        "last_impact_summary": last_impact.get("summary") if last_impact else None,
        "last_qdrant_sync": last_qdrant_sync,
        "recovery_actions": _recovery_actions(manifest.pending_changes, cfg.vector_store.provider, last_qdrant_sync),
        "operations_summary": build_rebuild_operations_summary(
            kb_name=kb_name,
            cfg=cfg,
            graph_state=graph_state,
            manifest=manifest,
        ),
    }


def export_dirty_state(kb_name: str, cfg: Settings, *, graph_state: GraphState | None = None) -> list[dict[str, Any]]:
    manifest = load_manifest(kb_name, cfg)
    records = {record.manual_id: record for record in list_records(kb_name, cfg, graph_state=graph_state)}
    rows: list[dict[str, Any]] = []
    for manual_id, dirty in sorted(manifest.dirty_manuals.items()):
        record = records.get(manual_id)
        rows.append(
            {
                "manual_id": manual_id,
                "source_file": dirty.source_file or (record.source_file if record else ""),
                "operation": dirty.operation,
                "updated_at": dirty.updated_at,
                "checksum": dirty.checksum or (record.checksum if record else ""),
                "status": record.status if record else "deleted",
                "searchable": bool(record.searchable) if record else False,
                "exists": bool(record.exists) if record else False,
            }
        )
    return rows


def _meta_dict(graph_state: GraphState | None) -> dict[str, Any]:
    return graph_state.meta if graph_state is not None and isinstance(graph_state.meta, dict) else {}


def _load_last_impact_summary(kb_name: str, cfg: Settings) -> dict[str, Any] | None:
    path = Path(cfg.storage.data_dir) / kb_name / "rebuild_impact.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _low_cardinality_qdrant_sync(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "provider": str(value.get("provider") or "qdrant"),
        "strategy": str(value.get("strategy") or ""),
        "points_upserted": int(value.get("points_upserted") or 0),
        "points_deleted": int(value.get("points_deleted") or 0),
        "points_reused": int(value.get("points_reused") or 0),
        "fallback_reason": str(value.get("fallback_reason") or ""),
    }


def _primary_recovery_hint(
    *,
    status: str,
    pending_changes: bool,
    provider: str,
    qdrant_sync: dict[str, Any] | None,
    fallback_reason: str,
    chunk_identity_fallback_reason: str,
) -> str:
    if not pending_changes and status in {"", "done"}:
        return "none"
    if provider == "qdrant" and status == "failed":
        return "check_qdrant_then_retry"
    if provider == "qdrant" and qdrant_sync and qdrant_sync.get("fallback_reason"):
        return "force_full_rebuild"
    if fallback_reason or chunk_identity_fallback_reason:
        return "force_full_rebuild"
    if pending_changes:
        return "retry_incremental" if status == "failed" else "inspect_dirty"
    return "none"


def _recovery_actions(pending_changes: bool, provider: str, last_qdrant_sync: dict[str, Any] | None) -> list[str]:
    if not pending_changes:
        return []
    actions = ["inspect_dirty", "retry_incremental", "force_full_rebuild"]
    if provider == "qdrant":
        actions.append("check_qdrant_then_retry")
        if last_qdrant_sync is None or last_qdrant_sync.get("fallback_reason"):
            actions.append("switch_to_npz_or_restore_qdrant")
    return actions


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


def _upsert_manual_registry(
    kb_name: str,
    metadata_data: dict[str, Any],
    file_bytes: bytes,
    cfg: Settings,
    *,
    overwrite: bool,
) -> ManualLibraryRecord:
    validation = validate_metadata(kb_name, metadata_data, cfg, mode="upsert")
    if not validation.valid or validation.normalized is None:
        _raise_validation_error(validation)
    metadata = validation.normalized
    registry = create_registry(cfg.manual_library.registry_path)
    existing = registry.get(kb_name, metadata.manual_id)
    source_duplicate = next((record for record in registry.list(kb_name) if record.source_file == metadata.source_file and record.manual_id != metadata.manual_id), None)
    if not overwrite and (existing is not None or source_duplicate is not None):
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Manual already exists. Set overwrite=true to replace it.",
            {"manual_id": metadata.manual_id, "source_file": metadata.source_file},
        )
    checksum = hashlib.sha256(file_bytes).hexdigest()
    metadata = replace(metadata, checksum=checksum, uploaded_at=metadata.uploaded_at or _now())
    next_version = (existing.version + 1) if existing is not None else 1
    blob_ref = create_blob_store(cfg).put(
        kb_name,
        metadata.manual_id,
        metadata.source_file,
        file_bytes,
        {"content_type": guess_content_type(metadata.source_file), "version": next_version},
    )
    record = registry.upsert(kb_name, metadata, blob_ref, operation="upsert")
    mark_dirty(kb_name, cfg, manual_id=metadata.manual_id, source_file=metadata.source_file, operation="upsert", checksum=checksum)
    return _record_from_registry(record, load_manifest(kb_name, cfg), graph_state=None)


def _update_manual_metadata_registry(
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
    registry_record = create_registry(cfg.manual_library.registry_path).update_metadata(kb_name, manual_id, validation.normalized)
    mark_dirty(
        kb_name,
        cfg,
        manual_id=manual_id,
        source_file=validation.normalized.source_file,
        operation="metadata_update",
        checksum=registry_record.checksum,
    )
    return _record_from_registry(registry_record, load_manifest(kb_name, cfg), graph_state=None)


def _replace_manual_file_registry(kb_name: str, manual_id: str, file_bytes: bytes, cfg: Settings) -> ManualLibraryRecord:
    registry = create_registry(cfg.manual_library.registry_path)
    current = registry.get(kb_name, manual_id)
    if current is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    checksum = hashlib.sha256(file_bytes).hexdigest()
    metadata = replace(current.metadata, checksum=checksum, uploaded_at=_now())
    blob_ref = create_blob_store(cfg).put(
        kb_name,
        manual_id,
        current.source_file,
        file_bytes,
        {"content_type": guess_content_type(current.source_file), "version": current.version + 1},
    )
    updated = registry.upsert(kb_name, metadata, blob_ref, operation="file_replace")
    mark_dirty(kb_name, cfg, manual_id=manual_id, source_file=current.source_file, operation="file_replace", checksum=checksum)
    return _record_from_registry(updated, load_manifest(kb_name, cfg), graph_state=None)


def _disable_manual_registry(kb_name: str, manual_id: str, cfg: Settings, *, archived: bool) -> ManualLibraryRecord:
    status = "archived" if archived else "disabled"
    operation = "archive" if archived else "disable"
    registry_record = create_registry(cfg.manual_library.registry_path).set_status(kb_name, manual_id, status, operation=operation)
    mark_dirty(kb_name, cfg, manual_id=manual_id, source_file=registry_record.source_file, operation=operation, checksum=registry_record.checksum)
    return _record_from_registry(registry_record, load_manifest(kb_name, cfg), graph_state=None)


def _delete_manual_registry(kb_name: str, manual_id: str, cfg: Settings) -> dict[str, Any]:
    registry = create_registry(cfg.manual_library.registry_path)
    current = registry.get(kb_name, manual_id)
    if current is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    deleted = registry.hard_delete(kb_name, manual_id)
    create_blob_store(cfg).delete(current.blob_key)
    mark_dirty(kb_name, cfg, manual_id=manual_id, source_file=current.source_file, operation="hard_delete", checksum=current.checksum)
    orphan_tags_removed = _cleanup_deleted_manual_tags(kb_name, manual_id, cfg)
    return {
        "manual_id": manual_id,
        "status": "deleted",
        "rebuild_required": True,
        "registry_backend": "sqlite",
        "registry_version": deleted.version,
        "orphan_tags_removed": orphan_tags_removed,
    }


def _cleanup_deleted_manual_tags(kb_name: str, manual_id: str, cfg: Settings) -> int:
    registry = create_registry(_phase0_registry_path(cfg))
    with registry.connection() as conn:
        with conn:
            delete_manual_tags(conn, kb_name, manual_id)
            orphans = find_orphan_tags(conn, kb_name)
            orphan_tags_removed = delete_tags(conn, orphans)
    if orphan_tags_removed:
        mark_epa_basis_dirty(cfg)
    return orphan_tags_removed


def _phase0_registry_path(cfg: Settings) -> str | Path:
    if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
        return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
    return cfg.manual_library.registry_path


def _list_records_registry(kb_name: str, cfg: Settings, *, graph_state: GraphState | None) -> list[ManualLibraryRecord]:
    manifest = load_manifest(kb_name, cfg)
    registry = create_registry(cfg.manual_library.registry_path)
    records = [_record_from_registry(record, manifest, graph_state=graph_state) for record in registry.list(kb_name)]
    return sorted(records, key=lambda record: record.manual_id)


def _record_from_registry(
    record: ManualRecord,
    manifest: ManualLibraryManifest,
    *,
    graph_state: GraphState | None,
) -> ManualLibraryRecord:
    chunk_count = None
    searchable = False
    if graph_state is not None:
        count = _chunk_count(graph_state, record.manual_id)
        chunk_count = count
        searchable = count > 0
    status = record.status if record.status in INACTIVE_STATUSES else "active"
    return ManualLibraryRecord(
        kb_name=record.kb_name,
        manual_id=record.manual_id,
        source_file=record.source_file,
        metadata=record.metadata,
        status=status,  # type: ignore[arg-type]
        exists=True,
        checksum=record.checksum,
        updated_at=record.updated_at,
        chunk_count=chunk_count,
        searchable=searchable,
        rebuild_required=manifest.pending_changes,
        storage_backend=record.blob_backend,
        blob_key=record.blob_key,
        size_bytes=record.size_bytes,
        content_type=record.content_type,
        registry_backend="sqlite",
        registry_version=record.version,
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
    for suffix in sorted({".htm", ".html", ".md", ".pdf", ".txt"}):
        candidate = sidecar.with_name(stem + suffix)
        if candidate.exists():
            return _relative(candidate, root)
    return _relative(sidecar.with_name(stem + ".md"), root)
