from __future__ import annotations

from dataclasses import dataclass
import hashlib
import mimetypes
import os
from pathlib import Path
import re
from typing import Any, Protocol

from .config import Settings
from .errors import ErrorCode, ServiceError
from .storage.atomic import atomic_write


@dataclass(frozen=True)
class BlobRef:
    backend: str
    blob_key: str
    checksum: str
    size_bytes: int
    content_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "blob_key": self.blob_key,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }


class ManualBlobStore(Protocol):
    backend: str

    def put(self, kb_name: str, manual_id: str, source_file: str, content: bytes, metadata: dict[str, object] | None = None) -> BlobRef:
        ...

    def get(self, blob_key: str) -> bytes:
        ...

    def delete(self, blob_key: str) -> None:
        ...

    def exists(self, blob_key: str) -> bool:
        ...


class LocalManualBlobStore:
    backend = "local"

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).expanduser().resolve()

    def put(self, kb_name: str, manual_id: str, source_file: str, content: bytes, metadata: dict[str, object] | None = None) -> BlobRef:
        checksum = hashlib.sha256(content).hexdigest()
        version = int((metadata or {}).get("version") or 1)
        content_type = str((metadata or {}).get("content_type") or guess_content_type(source_file))
        key = make_local_blob_key(kb_name, manual_id, version, checksum, source_file)
        path = self._path_for_key(key)

        def write(tmp_path: Path) -> None:
            tmp_path.write_bytes(content)

        atomic_write(path, write)
        return BlobRef(
            backend=self.backend,
            blob_key=key,
            checksum=checksum,
            size_bytes=len(content),
            content_type=content_type,
        )

    def get(self, blob_key: str) -> bytes:
        path = self._path_for_key(blob_key)
        if not path.exists():
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Manual blob is missing.", {"blob_key": blob_key})
        return path.read_bytes()

    def delete(self, blob_key: str) -> None:
        self._path_for_key(blob_key).unlink(missing_ok=True)

    def exists(self, blob_key: str) -> bool:
        return self._path_for_key(blob_key).exists()

    def _path_for_key(self, blob_key: str) -> Path:
        key_path = Path(blob_key)
        if key_path.is_absolute() or any(part in {"", ".", ".."} for part in key_path.parts):
            raise ServiceError(ErrorCode.INVALID_INPUT, "blob_key must be a safe relative path.", {"blob_key": blob_key})
        path = (self.root_dir / key_path).resolve()
        try:
            path.relative_to(self.root_dir)
        except ValueError as exc:
            raise ServiceError(ErrorCode.INVALID_INPUT, "blob_key escapes blob root.", {"blob_key": blob_key}) from exc
        return path


class S3ManualBlobStore:
    backend = "s3"

    def __init__(self, bucket: str, prefix: str = "", *, client: Any):
        self.bucket = bucket.strip()
        self.prefix = normalize_s3_prefix(prefix)
        self.client = client
        if not self.bucket:
            raise ServiceError(ErrorCode.INVALID_CONFIG, "manual_library.s3_bucket is required for S3 blob storage.", {"blob_backend": self.backend})

    def put(self, kb_name: str, manual_id: str, source_file: str, content: bytes, metadata: dict[str, object] | None = None) -> BlobRef:
        checksum = hashlib.sha256(content).hexdigest()
        version = int((metadata or {}).get("version") or 1)
        content_type = str((metadata or {}).get("content_type") or guess_content_type(source_file))
        key = make_s3_blob_key(self.prefix, kb_name, manual_id, version, checksum, source_file)
        object_metadata = {
            "checksum": checksum,
            "manual_id": _s3_metadata_value(manual_id),
            "source_file": _s3_metadata_value(_safe_basename(source_file)),
            "content_type": _s3_metadata_value(content_type),
            "version": str(version),
        }
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata=object_metadata,
            )
        except Exception as exc:
            raise _s3_operation_error("put", self.bucket, key, exc) from exc
        return BlobRef(
            backend=self.backend,
            blob_key=key,
            checksum=checksum,
            size_bytes=len(content),
            content_type=content_type,
        )

    def get(self, blob_key: str) -> bytes:
        key = _validate_s3_blob_key(blob_key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            return body.read()
        except Exception as exc:
            if _is_not_found_error(exc):
                raise ServiceError(
                    ErrorCode.STORAGE_LOAD_FAILED,
                    "Manual blob is missing.",
                    {"blob_backend": self.backend, "bucket": self.bucket, "blob_key": key, "operation": "get", "error_code": _client_error_code(exc)},
                ) from exc
            raise _s3_operation_error("get", self.bucket, key, exc) from exc

    def delete(self, blob_key: str) -> None:
        key = _validate_s3_blob_key(blob_key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if not _is_not_found_error(exc):
                raise _s3_operation_error("delete", self.bucket, key, exc) from exc

    def exists(self, blob_key: str) -> bool:
        key = _validate_s3_blob_key(blob_key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise _s3_operation_error("head", self.bucket, key, exc) from exc


def create_blob_store(cfg: Settings) -> ManualBlobStore:
    if cfg.manual_library.blob_backend == "local":
        return LocalManualBlobStore(cfg.manual_library.blob_root_dir)
    if cfg.manual_library.blob_backend == "s3":
        return S3ManualBlobStore(
            cfg.manual_library.s3_bucket,
            cfg.manual_library.s3_prefix,
            client=_create_s3_client(cfg),
        )
    raise ServiceError(
        ErrorCode.INVALID_CONFIG,
        "Configured manual blob backend is not implemented in this build.",
        {"blob_backend": cfg.manual_library.blob_backend},
    )


def make_local_blob_key(kb_name: str, manual_id: str, version: int, checksum: str, source_file: str) -> str:
    safe_kb = _safe_segment(kb_name)
    safe_manual = _safe_segment(manual_id)
    basename = _safe_basename(source_file)
    digest = checksum[:16] if checksum else "missing-checksum"
    return f"{safe_kb}/{safe_manual}/{version}/{digest}-{basename}"


def make_s3_blob_key(prefix: str, kb_name: str, manual_id: str, version: int, checksum: str, source_file: str) -> str:
    local_key = make_local_blob_key(kb_name, manual_id, version, checksum, source_file)
    normalized_prefix = normalize_s3_prefix(prefix)
    return f"{normalized_prefix}/{local_key}" if normalized_prefix else local_key


def normalize_s3_prefix(prefix: str) -> str:
    parts = [part for part in str(prefix).replace("\\", "/").split("/") if part not in {"", "."}]
    safe_parts = [_safe_segment(part) for part in parts if part != ".."]
    return "/".join(safe_parts)


def guess_content_type(source_file: str) -> str:
    content_type, _ = mimetypes.guess_type(source_file)
    if content_type:
        return content_type
    suffix = Path(source_file).suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    if suffix == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip(".-")
    return normalized or "item"


def _safe_basename(source_file: str) -> str:
    basename = os.path.basename(str(source_file).replace("\\", "/"))
    return _safe_segment(basename)


def _create_s3_client(cfg: Settings) -> Any:
    manual_cfg = cfg.manual_library
    if not manual_cfg.s3_bucket.strip():
        raise ServiceError(ErrorCode.INVALID_CONFIG, "manual_library.s3_bucket is required for S3 blob storage.", {"blob_backend": "s3"})
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ServiceError(
            ErrorCode.INVALID_CONFIG,
            "boto3 is required when manual_library.blob_backend=s3.",
            {"dependency": "boto3", "extra": "s3"},
        ) from exc
    access_key = _credential_from_env(manual_cfg.s3_access_key_env, required=bool(manual_cfg.s3_access_key_env.strip()))
    secret_key = _credential_from_env(manual_cfg.s3_secret_key_env, required=bool(manual_cfg.s3_secret_key_env.strip()))
    session_token = _credential_from_env(manual_cfg.s3_session_token_env, required=False)
    return boto3.client(
        "s3",
        endpoint_url=manual_cfg.s3_endpoint_url or None,
        region_name=manual_cfg.s3_region or "us-east-1",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        config=Config(
            connect_timeout=manual_cfg.s3_timeout_seconds,
            read_timeout=manual_cfg.s3_timeout_seconds,
            retries={"mode": "standard", "total_max_attempts": 3},
            s3={"addressing_style": manual_cfg.s3_addressing_style},
        ),
    )


def _credential_from_env(env_name: str, *, required: bool) -> str | None:
    name = env_name.strip()
    if not name:
        return None
    value = os.environ.get(name)
    if required and not value:
        raise ServiceError(
            ErrorCode.INVALID_CONFIG,
            "Configured S3 credential environment variable is not set.",
            {"env": name, "blob_backend": "s3"},
        )
    return value or None


def _validate_s3_blob_key(blob_key: str) -> str:
    key = str(blob_key).strip().replace("\\", "/")
    parts = key.split("/")
    if not key or key.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ServiceError(ErrorCode.INVALID_INPUT, "blob_key must be a safe S3 object key.", {"blob_key": blob_key, "blob_backend": "s3"})
    return key


def _s3_metadata_value(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:1024]


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            return str(error.get("Code") or "")
    return str(getattr(exc, "code", "") or "")


def _is_not_found_error(exc: Exception) -> bool:
    code = _client_error_code(exc)
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


def _s3_operation_error(operation: str, bucket: str, blob_key: str, exc: Exception) -> ServiceError:
    return ServiceError(
        ErrorCode.STORAGE_LOAD_FAILED,
        "S3 manual blob operation failed.",
        {
            "blob_backend": "s3",
            "bucket": bucket,
            "blob_key": blob_key,
            "operation": operation,
            "error_code": _client_error_code(exc),
        },
    )
