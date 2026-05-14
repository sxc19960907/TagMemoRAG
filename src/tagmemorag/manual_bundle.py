from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import uuid
import zipfile
from typing import Any, Literal

from . import __version__
from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_blob_store import create_blob_store, guess_content_type
from .manual_library import (
    build_dirty_state_report,
    delete_manual,
    list_records,
    mark_dirty,
    metadata_to_dict,
    registry_enabled,
    safe_source_path,
    upsert_manual,
)
from .manual_registry import create_registry
from .manuals import ManualMetadata

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_MANIFEST_PATH = "tagmemorag-bundle.json"
BUNDLE_CHECKSUMS_PATH = "checksums.json"
SUPPORTED_TOP_LEVELS = {"tagmemorag-bundle.json", "checksums.json", "records", "blobs", "audit", "state"}
ConflictMode = Literal["fail", "skip", "overwrite"]


@dataclass(frozen=True)
class BundleExportResult:
    bundle_path: str
    kb_name: str
    manual_count: int
    blob_count: int
    audit_event_count: int
    total_blob_bytes: int
    checksum_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_path": self.bundle_path,
            "kb_name": self.kb_name,
            "manual_count": self.manual_count,
            "blob_count": self.blob_count,
            "audit_event_count": self.audit_event_count,
            "total_blob_bytes": self.total_blob_bytes,
            "checksum_count": self.checksum_count,
        }


@dataclass(frozen=True)
class BundleConflict:
    manual_id: str
    source_file: str
    conflict_type: str
    existing_manual_id: str = ""
    existing_source_file: str = ""
    existing_checksum: str = ""
    incoming_checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "conflict_type": self.conflict_type,
            "existing_manual_id": self.existing_manual_id,
            "existing_source_file": self.existing_source_file,
            "existing_checksum": self.existing_checksum,
            "incoming_checksum": self.incoming_checksum,
        }


@dataclass(frozen=True)
class BundleImportAction:
    manual_id: str
    source_file: str
    action: Literal["create", "overwrite", "skip", "unchanged", "conflict"]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"manual_id": self.manual_id, "source_file": self.source_file, "action": self.action, "reason": self.reason}


@dataclass(frozen=True)
class BundleInspectReport:
    bundle_path: str
    valid: bool
    schema_version: int | None = None
    source_kb_name: str = ""
    target_kb_name: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    checksum_verified: bool = False
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[BundleConflict] = field(default_factory=list)
    import_actions: list[BundleImportAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_path": self.bundle_path,
            "valid": self.valid,
            "schema_version": self.schema_version,
            "source_kb_name": self.source_kb_name,
            "target_kb_name": self.target_kb_name,
            "counts": self.counts,
            "status_counts": self.status_counts,
            "checksum_verified": self.checksum_verified,
            "errors": self.errors,
            "warnings": self.warnings,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "import_actions": [action.to_dict() for action in self.import_actions],
        }


@dataclass(frozen=True)
class BundleImportResult:
    bundle_path: str
    source_kb_name: str
    target_kb_name: str
    dry_run: bool
    conflict_mode: ConflictMode
    imported_count: int
    skipped_count: int
    unchanged_count: int
    conflict_count: int
    actions: list[BundleImportAction]
    conflicts: list[BundleConflict]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_path": self.bundle_path,
            "source_kb_name": self.source_kb_name,
            "target_kb_name": self.target_kb_name,
            "dry_run": self.dry_run,
            "conflict_mode": self.conflict_mode,
            "imported_count": self.imported_count,
            "skipped_count": self.skipped_count,
            "unchanged_count": self.unchanged_count,
            "conflict_count": self.conflict_count,
            "actions": [action.to_dict() for action in self.actions],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


def export_bundle(kb_name: str, cfg: Settings, output_path: str | Path) -> BundleExportResult:
    records = [record for record in list_records(kb_name, cfg) if record.status != "deleted" and record.exists]
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: dict[str, bytes] = {}
    manifest_records: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []
    total_blob_bytes = 0

    if registry_enabled(cfg):
        registry_records = {record.manual_id: record for record in create_registry(cfg.manual_library.registry_path).list(kb_name)}
        blob_store = create_blob_store(cfg)
        for record in records:
            registry_record = registry_records.get(record.manual_id)
            if registry_record is None:
                continue
            blob_bytes = blob_store.get(registry_record.blob_key)
            if hashlib.sha256(blob_bytes).hexdigest() != registry_record.checksum:
                raise ServiceError(
                    ErrorCode.STORAGE_LOAD_FAILED,
                    "Registry blob checksum does not match the manual record.",
                    {"manual_id": record.manual_id, "blob_backend": registry_record.blob_backend},
                )
            blob_path = _blob_path(record.manual_id, registry_record.version, record.source_file, registry_record.checksum)
            record_payload = _record_payload(
                kb_name=kb_name,
                record=record,
                blob_path=blob_path,
                source_backend=registry_record.blob_backend,
                source_blob_key=registry_record.blob_key,
                version=registry_record.version,
            )
            _add_json_entry(entries, f"records/{_safe_segment(record.manual_id)}.json", record_payload)
            entries[blob_path] = blob_bytes
            total_blob_bytes += len(blob_bytes)
            manifest_records.append(_manifest_record(record, blob_path, record_payload))
        audit_events = [_safe_audit_event(event) for event in create_registry(cfg.manual_library.registry_path).audit_events(kb_name)]
    else:
        for record in records:
            source_path = safe_source_path(kb_name, record.source_file, cfg)
            blob_bytes = source_path.read_bytes()
            checksum = hashlib.sha256(blob_bytes).hexdigest()
            blob_path = _blob_path(record.manual_id, record.registry_version or 1, record.source_file, checksum)
            record_payload = _record_payload(
                kb_name=kb_name,
                record=record,
                blob_path=blob_path,
                source_backend="file",
                source_blob_key="",
                version=record.registry_version or 1,
                checksum=checksum,
                size_bytes=len(blob_bytes),
                content_type=record.content_type or guess_content_type(record.source_file),
            )
            _add_json_entry(entries, f"records/{_safe_segment(record.manual_id)}.json", record_payload)
            entries[blob_path] = blob_bytes
            total_blob_bytes += len(blob_bytes)
            manifest_records.append(_manifest_record(record, blob_path, record_payload))

    dirty_report = build_dirty_state_report(kb_name, cfg)
    _add_json_entry(entries, "state/dirty.json", dirty_report)
    _add_rebuild_impact_entry(entries, kb_name, cfg)
    if audit_events:
        entries["audit/events.jsonl"] = "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in audit_events).encode("utf-8")

    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": str(uuid.uuid4()),
        "created_at": _now(),
        "kb_name": kb_name,
        "source": {
            "registry_backend": cfg.manual_library.registry_backend,
            "blob_backend": cfg.manual_library.blob_backend if registry_enabled(cfg) else "file",
            "tagmemorag_version": __version__,
        },
        "counts": {
            "manual_count": len(manifest_records),
            "blob_count": len(manifest_records),
            "audit_event_count": len(audit_events),
            "dirty_manual_count": int(dirty_report.get("dirty_manual_count") or 0),
            "total_blob_bytes": total_blob_bytes,
        },
        "records": sorted(manifest_records, key=lambda item: str(item["manual_id"])),
    }
    _add_json_entry(entries, BUNDLE_MANIFEST_PATH, manifest)
    checksums = {"algorithm": "sha256", "entries": {path: _sha256_bytes(data) for path, data in sorted(entries.items())}}
    _add_json_entry(entries, BUNDLE_CHECKSUMS_PATH, checksums)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(entries):
            info = zipfile.ZipInfo(path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[path])

    return BundleExportResult(
        bundle_path=str(output),
        kb_name=kb_name,
        manual_count=len(manifest_records),
        blob_count=len(manifest_records),
        audit_event_count=len(audit_events),
        total_blob_bytes=total_blob_bytes,
        checksum_count=len(checksums["entries"]),
    )


def inspect_bundle(
    bundle_path: str | Path,
    cfg: Settings | None = None,
    *,
    target_kb: str | None = None,
    conflict_mode: ConflictMode = "fail",
) -> BundleInspectReport:
    try:
        loaded = _load_bundle(bundle_path)
        actions, conflicts = _plan_actions(loaded["records"], target_kb or loaded["manifest"]["kb_name"], cfg, conflict_mode)
        return _report_from_loaded(loaded, True, target_kb=target_kb, actions=actions, conflicts=conflicts)
    except ServiceError as exc:
        return BundleInspectReport(
            bundle_path=str(Path(bundle_path).expanduser()),
            valid=False,
            errors=[exc.to_dict()],
        )


def import_bundle(
    bundle_path: str | Path,
    cfg: Settings,
    *,
    target_kb: str | None = None,
    conflict_mode: ConflictMode = "fail",
    dry_run: bool = False,
) -> BundleImportResult:
    loaded = _load_bundle(bundle_path)
    source_kb = str(loaded["manifest"]["kb_name"])
    resolved_target = target_kb or source_kb
    actions, conflicts = _plan_actions(loaded["records"], resolved_target, cfg, conflict_mode)
    if conflict_mode == "fail" and conflicts:
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Bundle import conflicts with existing target manuals.",
            {"conflicts": [conflict.to_dict() for conflict in conflicts]},
        )
    if not dry_run:
        records_by_id = {str(record["manual_id"]): record for record in loaded["records"]}
        conflicts_by_id = {conflict.manual_id: conflict for conflict in conflicts}
        with zipfile.ZipFile(Path(bundle_path).expanduser(), "r") as archive:
            for action in actions:
                if action.action not in {"create", "overwrite"}:
                    continue
                record = records_by_id[action.manual_id]
                conflict = conflicts_by_id.get(action.manual_id)
                if (
                    action.action == "overwrite"
                    and conflict is not None
                    and conflict.conflict_type == "source_file"
                    and conflict.existing_manual_id
                    and conflict.existing_manual_id != action.manual_id
                ):
                    delete_manual(resolved_target, conflict.existing_manual_id, cfg)
                blob_path = str(record["blob"]["path"])
                blob_bytes = archive.read(blob_path)
                metadata = dict(record["metadata"])
                metadata["source_file"] = record["source_file"]
                metadata["manual_id"] = record["manual_id"]
                metadata["checksum"] = _sha256_bytes(blob_bytes)
                upsert_manual(resolved_target, metadata, blob_bytes, cfg, overwrite=action.action == "overwrite")
                mark_dirty(
                    resolved_target,
                    cfg,
                    manual_id=action.manual_id,
                    source_file=action.source_file,
                    operation="bundle_import",
                    checksum=str(metadata["checksum"]),
                )
    imported = len([action for action in actions if action.action in {"create", "overwrite"}])
    skipped = len([action for action in actions if action.action == "skip"])
    unchanged = len([action for action in actions if action.action == "unchanged"])
    return BundleImportResult(
        bundle_path=str(Path(bundle_path).expanduser()),
        source_kb_name=source_kb,
        target_kb_name=resolved_target,
        dry_run=dry_run,
        conflict_mode=conflict_mode,
        imported_count=0 if dry_run else imported,
        skipped_count=skipped,
        unchanged_count=unchanged,
        conflict_count=len(conflicts),
        actions=actions,
        conflicts=conflicts,
    )


def _load_bundle(bundle_path: str | Path) -> dict[str, Any]:
    path = Path(bundle_path).expanduser()
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle is not a readable ZIP archive.", {"bundle_path": str(path)}) from exc
    with archive:
        names = archive.namelist()
        _validate_entry_names(names)
        if BUNDLE_MANIFEST_PATH not in names:
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle manifest is missing.", {"required_path": BUNDLE_MANIFEST_PATH})
        if BUNDLE_CHECKSUMS_PATH not in names:
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle checksums are missing.", {"required_path": BUNDLE_CHECKSUMS_PATH})
        manifest = _read_json(archive, BUNDLE_MANIFEST_PATH)
        if int(manifest.get("schema_version") or 0) != BUNDLE_SCHEMA_VERSION:
            raise ServiceError(
                ErrorCode.STORAGE_SCHEMA_MISMATCH,
                "Bundle schema version is not supported.",
                {"expected": BUNDLE_SCHEMA_VERSION, "actual": manifest.get("schema_version")},
            )
        _verify_checksums(archive)
        records = [_read_json(archive, str(item["record_path"])) for item in manifest.get("records", []) if isinstance(item, dict)]
        if len(records) != int(manifest.get("counts", {}).get("manual_count") or len(records)):
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle record count does not match the manifest.", {})
        for record in records:
            _validate_record(record, archive)
        audit_event_count = _count_jsonl(archive, "audit/events.jsonl") if "audit/events.jsonl" in names else 0
        return {
            "path": str(path),
            "manifest": manifest,
            "records": records,
            "audit_event_count": audit_event_count,
            "checksum_count": len(_read_json(archive, BUNDLE_CHECKSUMS_PATH).get("entries", {})),
        }


def _plan_actions(
    records: list[dict[str, Any]],
    target_kb: str,
    cfg: Settings | None,
    conflict_mode: ConflictMode,
) -> tuple[list[BundleImportAction], list[BundleConflict]]:
    actions: list[BundleImportAction] = []
    conflicts: list[BundleConflict] = []
    existing_by_id = {}
    existing_by_source = {}
    if cfg is not None:
        existing = list_records(target_kb, cfg)
        existing_by_id = {record.manual_id: record for record in existing}
        existing_by_source = {record.source_file: record for record in existing}
    for record in sorted(records, key=lambda item: str(item.get("manual_id", ""))):
        manual_id = str(record["manual_id"])
        source_file = str(record["source_file"])
        checksum = str(record["checksum"])
        id_match = existing_by_id.get(manual_id)
        source_match = existing_by_source.get(source_file)
        conflict = None
        if id_match is not None:
            conflict = BundleConflict(manual_id, source_file, "manual_id", manual_id, id_match.source_file, id_match.checksum, checksum)
        elif source_match is not None:
            conflict = BundleConflict(manual_id, source_file, "source_file", source_match.manual_id, source_file, source_match.checksum, checksum)
        if conflict is None:
            actions.append(BundleImportAction(manual_id, source_file, "create"))
        elif conflict.existing_checksum == checksum and conflict.existing_manual_id == manual_id:
            actions.append(BundleImportAction(manual_id, source_file, "unchanged", "same_checksum"))
        elif conflict_mode == "skip":
            conflicts.append(conflict)
            actions.append(BundleImportAction(manual_id, source_file, "skip", conflict.conflict_type))
        elif conflict_mode == "overwrite":
            conflicts.append(conflict)
            actions.append(BundleImportAction(manual_id, source_file, "overwrite", conflict.conflict_type))
        else:
            conflicts.append(conflict)
            actions.append(BundleImportAction(manual_id, source_file, "conflict", conflict.conflict_type))
    return actions, conflicts


def _report_from_loaded(
    loaded: dict[str, Any],
    valid: bool,
    *,
    target_kb: str | None,
    actions: list[BundleImportAction],
    conflicts: list[BundleConflict],
) -> BundleInspectReport:
    records = loaded["records"]
    status_counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "active")
        status_counts[status] = status_counts.get(status, 0) + 1
    manifest = loaded["manifest"]
    counts = dict(manifest.get("counts") or {})
    counts["checksum_count"] = int(loaded.get("checksum_count") or 0)
    counts["audit_event_count"] = int(loaded.get("audit_event_count") or 0)
    return BundleInspectReport(
        bundle_path=str(loaded["path"]),
        valid=valid,
        schema_version=int(manifest.get("schema_version")),
        source_kb_name=str(manifest.get("kb_name") or ""),
        target_kb_name=target_kb or "",
        counts={str(key): int(value) for key, value in counts.items() if isinstance(value, int)},
        status_counts=status_counts,
        checksum_verified=True,
        conflicts=conflicts,
        import_actions=actions,
    )


def _validate_entry_names(names: list[str]) -> None:
    seen: set[str] = set()
    for name in names:
        safe = safe_bundle_path(name)
        if safe in seen:
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle contains duplicate archive entries.", {"path": safe})
        seen.add(safe)
        top = safe.split("/", 1)[0]
        if top not in SUPPORTED_TOP_LEVELS:
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle contains an unsupported top-level path.", {"path": safe})


def safe_bundle_path(path: str) -> str:
    value = str(path).replace("\\", "/")
    posix = PurePosixPath(value)
    if not value or value.endswith("/") or value.startswith("/") or posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle path must be a safe relative path.", {"path": path})
    return posix.as_posix()


def _verify_checksums(archive: zipfile.ZipFile) -> None:
    checksums = _read_json(archive, BUNDLE_CHECKSUMS_PATH)
    if checksums.get("algorithm") != "sha256" or not isinstance(checksums.get("entries"), dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle checksums metadata is malformed.", {})
    names = set(archive.namelist())
    for path, expected in checksums["entries"].items():
        safe_path = safe_bundle_path(str(path))
        if safe_path == BUNDLE_CHECKSUMS_PATH:
            raise ServiceError(ErrorCode.INVALID_INPUT, "checksums.json must not include itself.", {})
        if safe_path not in names:
            raise ServiceError(ErrorCode.INVALID_INPUT, "Checksummed bundle entry is missing.", {"path": safe_path})
        actual = _sha256_bytes(archive.read(safe_path))
        if actual != str(expected):
            raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle checksum mismatch.", {"path": safe_path})


def _validate_record(record: dict[str, Any], archive: zipfile.ZipFile) -> None:
    required = {"schema_version", "manual_id", "source_file", "metadata", "status", "checksum", "blob"}
    missing = sorted(required - set(record))
    if missing:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle record metadata is malformed.", {"missing": missing})
    if int(record.get("schema_version") or 0) != BUNDLE_SCHEMA_VERSION:
        raise ServiceError(ErrorCode.STORAGE_SCHEMA_MISMATCH, "Bundle record schema version is not supported.", {"manual_id": record.get("manual_id")})
    ManualMetadata.from_dict(dict(record["metadata"]))
    blob = record.get("blob")
    if not isinstance(blob, dict) or not blob.get("path"):
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle record blob metadata is malformed.", {"manual_id": record.get("manual_id")})
    blob_path = safe_bundle_path(str(blob["path"]))
    if blob_path not in archive.namelist():
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle blob entry is missing.", {"manual_id": record.get("manual_id"), "blob_path": blob_path})
    if _sha256_bytes(archive.read(blob_path)) != str(record["checksum"]):
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle blob checksum mismatch.", {"manual_id": record.get("manual_id"), "blob_path": blob_path})


def _record_payload(
    *,
    kb_name: str,
    record: Any,
    blob_path: str,
    source_backend: str,
    source_blob_key: str,
    version: int,
    checksum: str | None = None,
    size_bytes: int | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    digest = checksum or record.checksum
    metadata = dict(metadata_to_dict(record.metadata) or {})
    metadata["checksum"] = digest
    metadata["source_file"] = record.source_file
    metadata["manual_id"] = record.manual_id
    blob: dict[str, Any] = {"path": blob_path, "source_backend": source_backend}
    if source_blob_key:
        blob["source_blob_key"] = source_blob_key
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "kb_name": kb_name,
        "manual_id": record.manual_id,
        "source_file": record.source_file,
        "metadata": metadata,
        "status": record.status,
        "version": int(version),
        "checksum": digest,
        "content_type": content_type or record.content_type or guess_content_type(record.source_file),
        "size_bytes": int(size_bytes if size_bytes is not None else record.size_bytes),
        "blob": blob,
        "created_at": "",
        "updated_at": record.updated_at,
    }


def _manifest_record(record: Any, blob_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    record_path = f"records/{_safe_segment(record.manual_id)}.json"
    return {
        "manual_id": record.manual_id,
        "record_path": record_path,
        "blob_path": blob_path,
        "checksum": str(payload["checksum"]),
    }


def _safe_audit_event(event: Any) -> dict[str, Any]:
    allowed_detail = {"source_file", "status", "checksum", "blob_backend", "size_bytes", "content_type"}
    return {
        "event_id": event.event_id,
        "kb_name": event.kb_name,
        "manual_id": event.manual_id,
        "operation": event.operation,
        "outcome": event.outcome,
        "version": event.version,
        "actor_id": event.actor_id,
        "created_at": event.created_at,
        "detail": {key: event.detail[key] for key in sorted(allowed_detail) if key in event.detail},
    }


def _blob_path(manual_id: str, version: int, source_file: str, checksum: str) -> str:
    return f"blobs/{_safe_segment(manual_id)}/{int(version)}/{checksum[:16]}-{_safe_segment(Path(source_file).name)}"


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(value)).strip(".-") or "item"


def _add_json_entry(entries: dict[str, bytes], path: str, data: Any) -> None:
    entries[path] = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _add_rebuild_impact_entry(entries: dict[str, bytes], kb_name: str, cfg: Settings) -> None:
    path = Path(cfg.storage.data_dir) / kb_name / "rebuild_impact.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        _add_json_entry(entries, "state/rebuild_impact.json", data)


def _read_json(archive: zipfile.ZipFile, path: str) -> dict[str, Any]:
    try:
        data = json.loads(archive.read(path).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle JSON entry is malformed.", {"path": path}) from exc
    if not isinstance(data, dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "Bundle JSON entry must be an object.", {"path": path})
    return data


def _count_jsonl(archive: zipfile.ZipFile, path: str) -> int:
    return len([line for line in archive.read(path).decode("utf-8").splitlines() if line.strip()])


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
