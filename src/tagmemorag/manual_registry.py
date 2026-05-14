from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Literal

from .errors import ErrorCode, ServiceError
from .manual_blob_store import BlobRef
from .manuals import ManualMetadata

ManualRegistryStatus = Literal["active", "disabled", "archived", "deleted"]


@dataclass(frozen=True)
class ManualRecord:
    kb_name: str
    manual_id: str
    source_file: str
    metadata: ManualMetadata
    status: ManualRegistryStatus
    checksum: str
    content_type: str
    size_bytes: int
    blob_backend: str
    blob_key: str
    version: int
    created_at: str
    updated_at: str
    created_by: str = ""
    updated_by: str = ""

    def to_blob_ref(self) -> BlobRef:
        return BlobRef(
            backend=self.blob_backend,
            blob_key=self.blob_key,
            checksum=self.checksum,
            size_bytes=self.size_bytes,
            content_type=self.content_type,
        )


@dataclass(frozen=True)
class ManualAuditEvent:
    event_id: str
    kb_name: str
    manual_id: str
    operation: str
    outcome: str
    version: int
    actor_id: str
    created_at: str
    detail: dict[str, Any]


@dataclass(frozen=True)
class RegistryMigrationReport:
    kb_name: str
    dry_run: bool
    imported_records: int = 0
    skipped_records: int = 0
    invalid_metadata: int = 0
    missing_files: int = 0
    duplicate_manual_ids: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "dry_run": self.dry_run,
            "imported_records": self.imported_records,
            "skipped_records": self.skipped_records,
            "invalid_metadata": self.invalid_metadata,
            "missing_files": self.missing_files,
            "duplicate_manual_ids": self.duplicate_manual_ids,
        }


class SQLiteManualRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def get(self, kb_name: str, manual_id: str, *, include_deleted: bool = False) -> ManualRecord | None:
        query = "SELECT * FROM manual_records WHERE kb_name=? AND manual_id=?"
        params: tuple[Any, ...] = (kb_name, manual_id)
        if not include_deleted:
            query += " AND status != 'deleted'"
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return _record_from_row(row) if row is not None else None

    def list(self, kb_name: str, *, include_deleted: bool = False) -> list[ManualRecord]:
        query = "SELECT * FROM manual_records WHERE kb_name=?"
        if not include_deleted:
            query += " AND status != 'deleted'"
        query += " ORDER BY manual_id"
        with self._connect() as conn:
            rows = conn.execute(query, (kb_name,)).fetchall()
        return [_record_from_row(row) for row in rows]

    def upsert(
        self,
        kb_name: str,
        metadata: ManualMetadata,
        blob_ref: BlobRef,
        *,
        operation: str,
        actor_id: str = "",
    ) -> ManualRecord:
        now = _now()
        status = _registry_status(metadata.status)
        metadata = replace(metadata, status=status, checksum=blob_ref.checksum)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM manual_records WHERE kb_name=? AND manual_id=?",
                (kb_name, metadata.manual_id),
            ).fetchone()
            if existing is None:
                version = 1
                created_at = now
                created_by = actor_id
            else:
                current = _record_from_row(existing)
                version = current.version + (1 if operation in {"file_replace", "upsert"} else 0)
                created_at = current.created_at
                created_by = current.created_by
            record = ManualRecord(
                kb_name=kb_name,
                manual_id=metadata.manual_id,
                source_file=metadata.source_file,
                metadata=metadata,
                status=status,
                checksum=blob_ref.checksum,
                content_type=blob_ref.content_type,
                size_bytes=blob_ref.size_bytes,
                blob_backend=blob_ref.backend,
                blob_key=blob_ref.blob_key,
                version=version,
                created_at=created_at,
                updated_at=now,
                created_by=created_by,
                updated_by=actor_id,
            )
            self._assert_source_unique(conn, record)
            conn.execute(
                """
                INSERT INTO manual_records (
                    kb_name, manual_id, source_file, status, metadata_json, checksum,
                    content_type, size_bytes, blob_backend, blob_key, version,
                    created_at, updated_at, created_by, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kb_name, manual_id) DO UPDATE SET
                    source_file=excluded.source_file,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    checksum=excluded.checksum,
                    content_type=excluded.content_type,
                    size_bytes=excluded.size_bytes,
                    blob_backend=excluded.blob_backend,
                    blob_key=excluded.blob_key,
                    version=excluded.version,
                    updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by
                """,
                _record_values(record),
            )
            self._insert_audit(conn, record, operation=operation, outcome="success", actor_id=actor_id, detail=_audit_detail(record))
        return record

    def update_metadata(self, kb_name: str, manual_id: str, metadata: ManualMetadata, *, actor_id: str = "") -> ManualRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM manual_records WHERE kb_name=? AND manual_id=? AND status != 'deleted'", (kb_name, manual_id)).fetchone()
            if row is None:
                raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
            current = _record_from_row(row)
            now = _now()
            status = _registry_status(metadata.status)
            metadata = replace(metadata, status=status, checksum=current.checksum)
            record = replace(current, source_file=metadata.source_file, metadata=metadata, status=status, updated_at=now, updated_by=actor_id)
            self._assert_source_unique(conn, record)
            conn.execute(
                """
                UPDATE manual_records
                SET source_file=?, status=?, metadata_json=?, updated_at=?, updated_by=?
                WHERE kb_name=? AND manual_id=?
                """,
                (record.source_file, record.status, _metadata_json(record), now, actor_id, kb_name, manual_id),
            )
            self._insert_audit(conn, record, operation="metadata_update", outcome="success", actor_id=actor_id, detail=_audit_detail(record))
        return record

    def set_status(self, kb_name: str, manual_id: str, status: ManualRegistryStatus, *, operation: str, actor_id: str = "") -> ManualRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM manual_records WHERE kb_name=? AND manual_id=? AND status != 'deleted'", (kb_name, manual_id)).fetchone()
            if row is None:
                raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
            current = _record_from_row(row)
            now = _now()
            metadata = replace(current.metadata, status=status)
            record = replace(current, metadata=metadata, status=status, updated_at=now, updated_by=actor_id)
            conn.execute(
                "UPDATE manual_records SET status=?, metadata_json=?, updated_at=?, updated_by=? WHERE kb_name=? AND manual_id=?",
                (status, _metadata_json(record), now, actor_id, kb_name, manual_id),
            )
            self._insert_audit(conn, record, operation=operation, outcome="success", actor_id=actor_id, detail={"status": status})
        return record

    def hard_delete(self, kb_name: str, manual_id: str, *, actor_id: str = "") -> ManualRecord:
        return self.set_status(kb_name, manual_id, "deleted", operation="delete", actor_id=actor_id)

    def audit_events(self, kb_name: str, manual_id: str | None = None) -> list[ManualAuditEvent]:
        query = "SELECT * FROM manual_audit_events WHERE kb_name=?"
        params: list[Any] = [kb_name]
        if manual_id is not None:
            query += " AND manual_id=?"
            params.append(manual_id)
        query += " ORDER BY created_at, event_id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_event_from_row(row) for row in rows]

    def _assert_source_unique(self, conn: sqlite3.Connection, record: ManualRecord) -> None:
        row = conn.execute(
            """
            SELECT manual_id FROM manual_records
            WHERE kb_name=? AND source_file=? AND manual_id != ? AND status != 'deleted'
            """,
            (record.kb_name, record.source_file, record.manual_id),
        ).fetchone()
        if row is not None:
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                "source_file already belongs to another manual.",
                {"source_file": record.source_file, "manual_id": str(row["manual_id"])},
            )

    def _insert_audit(
        self,
        conn: sqlite3.Connection,
        record: ManualRecord,
        *,
        operation: str,
        outcome: str,
        actor_id: str,
        detail: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO manual_audit_events (
                event_id, kb_name, manual_id, operation, outcome, version,
                actor_id, created_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                record.kb_name,
                record.manual_id,
                operation,
                outcome,
                record.version,
                actor_id,
                _now(),
                json.dumps(detail, ensure_ascii=False, sort_keys=True),
            ),
        )

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_records(
                    kb_name TEXT NOT NULL,
                    manual_id TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    blob_backend TEXT NOT NULL,
                    blob_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (kb_name, manual_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_audit_events(
                    event_id TEXT PRIMARY KEY,
                    kb_name TEXT NOT NULL,
                    manual_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    actor_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    detail_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_records_kb_status ON manual_records(kb_name, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_audit_manual ON manual_audit_events(kb_name, manual_id, created_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn


def create_registry(path: str | Path) -> SQLiteManualRegistry:
    return SQLiteManualRegistry(path)


def _record_from_row(row: sqlite3.Row) -> ManualRecord:
    metadata = ManualMetadata.from_dict(json.loads(str(row["metadata_json"])))
    return ManualRecord(
        kb_name=str(row["kb_name"]),
        manual_id=str(row["manual_id"]),
        source_file=str(row["source_file"]),
        metadata=metadata,
        status=_registry_status(str(row["status"])),
        checksum=str(row["checksum"]),
        content_type=str(row["content_type"]),
        size_bytes=int(row["size_bytes"]),
        blob_backend=str(row["blob_backend"]),
        blob_key=str(row["blob_key"]),
        version=int(row["version"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
    )


def _event_from_row(row: sqlite3.Row) -> ManualAuditEvent:
    return ManualAuditEvent(
        event_id=str(row["event_id"]),
        kb_name=str(row["kb_name"]),
        manual_id=str(row["manual_id"]),
        operation=str(row["operation"]),
        outcome=str(row["outcome"]),
        version=int(row["version"]),
        actor_id=str(row["actor_id"]),
        created_at=str(row["created_at"]),
        detail=json.loads(str(row["detail_json"])),
    )


def _record_values(record: ManualRecord) -> tuple[Any, ...]:
    return (
        record.kb_name,
        record.manual_id,
        record.source_file,
        record.status,
        _metadata_json(record),
        record.checksum,
        record.content_type,
        record.size_bytes,
        record.blob_backend,
        record.blob_key,
        record.version,
        record.created_at,
        record.updated_at,
        record.created_by,
        record.updated_by,
    )


def _metadata_json(record: ManualRecord) -> str:
    from .manual_library import metadata_to_dict

    return json.dumps(metadata_to_dict(record.metadata), ensure_ascii=False, sort_keys=True)


def _audit_detail(record: ManualRecord) -> dict[str, Any]:
    return {
        "source_file": record.source_file,
        "status": record.status,
        "checksum": record.checksum,
        "blob_backend": record.blob_backend,
        "size_bytes": record.size_bytes,
    }


def _registry_status(status: str) -> ManualRegistryStatus:
    normalized = status.strip().lower()
    if normalized in {"", "active"}:
        return "active"
    if normalized in {"disabled", "archived", "deleted"}:
        return normalized  # type: ignore[return-value]
    raise ServiceError(ErrorCode.INVALID_INPUT, "manual status must be active, disabled, archived, or deleted.", {"status": status})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
