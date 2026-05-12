from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    KB_NOT_LOADED = "KB_NOT_LOADED"
    REBUILD_IN_PROGRESS = "REBUILD_IN_PROGRESS"
    REBUILD_FAILED = "REBUILD_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_CONFIG = "INVALID_CONFIG"
    STORAGE_LOAD_FAILED = "STORAGE_LOAD_FAILED"
    STORAGE_SCHEMA_MISMATCH = "STORAGE_SCHEMA_MISMATCH"
    ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    INTERNAL = "INTERNAL"


class ServiceError(Exception):
    def __init__(self, code: ErrorCode | str, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = ErrorCode(code) if not isinstance(code, ErrorCode) else code
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code.value, "message": self.message, "detail": self.detail}


class KbNotLoadedError(ServiceError):
    def __init__(self, kb_name: str = "default"):
        super().__init__(ErrorCode.KB_NOT_LOADED, f"Knowledge base is not loaded: {kb_name}", {"kb_name": kb_name})


class RebuildInProgressError(ServiceError):
    def __init__(self, task_id: str | None = None):
        detail = {"task_id": task_id} if task_id else {}
        super().__init__(ErrorCode.REBUILD_IN_PROGRESS, "A rebuild is already running.", detail)


class RebuildFailedError(ServiceError):
    def __init__(self, detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.REBUILD_FAILED, "Rebuild failed.", detail)


class ShuttingDownError(ServiceError):
    def __init__(self):
        super().__init__(ErrorCode.SHUTTING_DOWN, "Service is shutting down.")


class EmbeddingError(ServiceError):
    def __init__(self, message: str = "Embedding request failed.", detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.EMBEDDING_FAILED, message, detail)


class InvalidConfigError(ServiceError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.INVALID_CONFIG, message, detail)


class StorageSchemaMismatchError(ServiceError):
    def __init__(self, expected: str, actual: str | None):
        super().__init__(
            ErrorCode.STORAGE_SCHEMA_MISMATCH,
            "Storage schema version is not supported.",
            {"expected": expected, "actual": actual},
        )


class AnchorNotFoundError(ServiceError):
    def __init__(self, anchor_key: str):
        super().__init__(ErrorCode.ANCHOR_NOT_FOUND, "Anchor not found.", {"anchor_key": anchor_key})
