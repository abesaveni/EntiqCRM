"""
Document storage backends. Bytes go here; the `documents` table is the index.

  local — files under STORAGE_DIR/<tenant>/<doc-id>/<safe-filename>. Dev and single-host.
  s3    — AWS S3 (boto3 imported lazily so the dependency is optional until used).

Keys are generated server-side and never derived from user input beyond a sanitised
filename, so a client can never address another tenant's object.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    name = (name or "file").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:120]


def make_key(tenant_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    return f"{tenant_id}/{doc_id}/{safe_filename(filename)}"


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("storage key escapes root")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()
            try:
                p.parent.rmdir()
            except OSError:
                pass


class S3Storage:
    def __init__(self, bucket: str, region: str):
        import boto3  # lazy: only required when the backend is S3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND == "s3":
            if not settings.AWS_S3_BUCKET:
                raise RuntimeError("STORAGE_BACKEND=s3 requires AWS_S3_BUCKET")
            _storage = S3Storage(settings.AWS_S3_BUCKET, settings.AWS_REGION)
        else:
            _storage = LocalStorage(settings.STORAGE_DIR)
    return _storage


def reset_storage_for_tests() -> None:
    global _storage
    _storage = None
