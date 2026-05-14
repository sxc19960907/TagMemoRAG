from __future__ import annotations

import builtins
from io import BytesIO

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings
from tagmemorag.errors import ServiceError
from tagmemorag.manual_blob_store import LocalManualBlobStore, S3ManualBlobStore, create_blob_store, make_s3_blob_key, normalize_s3_prefix


class FakeS3ClientError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.fail_put = False

    def put_object(self, **kwargs):
        if self.fail_put:
            raise FakeS3ClientError("AccessDenied")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs.get("ContentType", ""),
            "Metadata": kwargs.get("Metadata", {}),
        }
        return {}

    def get_object(self, **kwargs):
        try:
            obj = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise FakeS3ClientError("NoSuchKey") from exc
        return {"Body": BytesIO(obj["Body"])}

    def head_object(self, **kwargs):
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise FakeS3ClientError("404")
        return {}

    def delete_object(self, **kwargs):
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)
        return {}


def test_local_blob_store_round_trip_uses_safe_relative_key(tmp_path):
    store = LocalManualBlobStore(tmp_path / "blobs")

    ref = store.put("default", "cm1", "coffee/cm1.md", b"# Manual\nSteam.\n", {"version": 3})

    assert ref.backend == "local"
    assert ref.blob_key == f"default/cm1/3/{ref.checksum[:16]}-cm1.md"
    assert ref.size_bytes == len(b"# Manual\nSteam.\n")
    assert ref.content_type == "text/markdown"
    assert store.exists(ref.blob_key)
    assert store.get(ref.blob_key) == b"# Manual\nSteam.\n"

    store.delete(ref.blob_key)
    assert not store.exists(ref.blob_key)


def test_local_blob_store_rejects_unsafe_blob_key(tmp_path):
    store = LocalManualBlobStore(tmp_path / "blobs")

    with pytest.raises(ServiceError) as exc:
        store.get("../escape.md")

    assert exc.value.code == "INVALID_INPUT"


def test_s3_prefix_and_key_generation_are_safe():
    assert normalize_s3_prefix("/manuals//prod/.././team/") == "manuals/prod/team"
    key = make_s3_blob_key("/manuals//prod", "default", "cm 1", 2, "abcdef1234567890", "/tmp/../cm1.md")

    assert key == "manuals/prod/default/cm-1/2/abcdef1234567890-cm1.md"
    assert ".." not in key
    assert not key.startswith("/")


def test_s3_blob_store_round_trip_uses_object_key_and_safe_metadata():
    client = FakeS3Client()
    store = S3ManualBlobStore("manuals", "/prod//", client=client)

    ref = store.put(
        "default",
        "cm1",
        "coffee/cm1.md",
        b"# Manual\nSteam.\n",
        {"version": 3, "content_type": "text/markdown"},
    )

    assert ref.backend == "s3"
    assert ref.blob_key == f"prod/default/cm1/3/{ref.checksum[:16]}-cm1.md"
    assert ref.size_bytes == len(b"# Manual\nSteam.\n")
    assert ref.content_type == "text/markdown"
    stored = client.objects[("manuals", ref.blob_key)]
    assert stored["ContentType"] == "text/markdown"
    assert stored["Metadata"]["checksum"] == ref.checksum
    assert stored["Metadata"]["manual_id"] == "cm1"
    assert stored["Metadata"]["source_file"] == "cm1.md"
    assert store.exists(ref.blob_key)
    assert store.get(ref.blob_key) == b"# Manual\nSteam.\n"

    store.delete(ref.blob_key)
    assert not store.exists(ref.blob_key)


def test_s3_blob_store_missing_get_raises_storage_error():
    store = S3ManualBlobStore("manuals", "", client=FakeS3Client())

    with pytest.raises(ServiceError) as exc:
        store.get("default/cm1/1/hash-cm1.md")

    assert exc.value.code == "STORAGE_LOAD_FAILED"
    assert exc.value.detail["operation"] == "get"
    assert exc.value.detail["error_code"] == "NoSuchKey"


def test_s3_blob_store_rejects_unsafe_blob_key():
    store = S3ManualBlobStore("manuals", "", client=FakeS3Client())

    with pytest.raises(ServiceError) as exc:
        store.exists("../escape.md")

    assert exc.value.code == "INVALID_INPUT"


def test_create_s3_blob_store_requires_bucket_before_dependency(monkeypatch):
    cfg = Settings(manual_library=ManualLibraryConfig(blob_backend="s3", s3_bucket=""))

    with pytest.raises(ServiceError) as exc:
        create_blob_store(cfg)

    assert exc.value.code == "INVALID_CONFIG"
    assert "s3_bucket" in exc.value.message


def test_create_s3_blob_store_missing_optional_dependency(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("No module named boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    cfg = Settings(manual_library=ManualLibraryConfig(blob_backend="s3", s3_bucket="manuals"))

    with pytest.raises(ServiceError) as exc:
        create_blob_store(cfg)

    assert exc.value.code == "INVALID_CONFIG"
    assert exc.value.detail == {"dependency": "boto3", "extra": "s3"}
