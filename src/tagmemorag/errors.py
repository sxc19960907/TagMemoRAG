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
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"
    INDEXGEN_NO_VERSION_DIFF = "INDEXGEN_NO_VERSION_DIFF"
    INDEXGEN_SHADOW_BUILD_IN_PROGRESS = "INDEXGEN_SHADOW_BUILD_IN_PROGRESS"
    INDEXGEN_NO_SHADOW = "INDEXGEN_NO_SHADOW"
    INDEXGEN_NO_READY_SHADOW = "INDEXGEN_NO_READY_SHADOW"
    INDEXGEN_ACTIVE_REBUILD_IN_PROGRESS = "INDEXGEN_ACTIVE_REBUILD_IN_PROGRESS"
    INDEXGEN_RETIRE_ACTIVE = "INDEXGEN_RETIRE_ACTIVE"
    INDEXGEN_RETIRE_SHADOW = "INDEXGEN_RETIRE_SHADOW"
    INDEXGEN_RETIRE_TOO_EARLY = "INDEXGEN_RETIRE_TOO_EARLY"
    INDEXGEN_NO_SUCH_GENERATION = "INDEXGEN_NO_SUCH_GENERATION"
    INDEXGEN_NO_SUCH_KB = "INDEXGEN_NO_SUCH_KB"
    INDEXGEN_SETTINGS_META_MISMATCH = "INDEXGEN_SETTINGS_META_MISMATCH"


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


class EmbeddingDimMismatchError(EmbeddingError):
    def __init__(self, expected_dim: int, actual_dim: int):
        super().__init__(
            "Embedding dimension does not match the configured model dimension.",
            {"expected_dim": expected_dim, "actual_dim": actual_dim},
        )


class InvalidConfigError(ServiceError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.INVALID_CONFIG, message, detail)


class UnauthorizedError(ServiceError):
    def __init__(self, message: str = "Missing or invalid Authorization.", detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.UNAUTHORIZED, message, detail)


class ForbiddenError(ServiceError):
    def __init__(self, message: str = "Forbidden.", detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.FORBIDDEN, message, detail)


class RateLimitedError(ServiceError):
    def __init__(self, detail: dict[str, Any] | None = None):
        super().__init__(ErrorCode.RATE_LIMITED, "Rate limit exceeded.", detail)


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
