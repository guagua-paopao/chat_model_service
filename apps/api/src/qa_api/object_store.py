from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from qa_api.config import Settings


class ObjectStoreError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class UploadGrant:
    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None


class ObjectStore(Protocol):
    quarantine_bucket: str
    published_bucket: str

    def initialize(self) -> None: ...

    def presign_put(self, *, version_id: str, key: str, content_type: str) -> UploadGrant: ...

    def receive_local_upload(self, *, token: str, content: bytes) -> tuple[str, str]: ...

    def stat(self, bucket: str, key: str) -> ObjectInfo: ...

    def read(self, bucket: str, key: str, *, max_bytes: int) -> bytes: ...

    def copy(
        self, source_bucket: str, source_key: str, target_bucket: str, target_key: str
    ) -> None: ...

    def delete(self, bucket: str, key: str) -> None: ...


class LocalObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.quarantine_bucket = settings.object_store_quarantine_bucket
        self.published_bucket = settings.object_store_published_bucket
        self._root = Path(settings.object_store_local_root).resolve()
        self._signing_key = (settings.cursor_signing_key or "").encode("utf-8")
        self._public_base = settings.upload_public_base_url.rstrip("/")
        self._expires_seconds = settings.upload_presign_seconds
        self._max_bytes = settings.ingestion_max_upload_bytes

    def initialize(self) -> None:
        self._path(self.quarantine_bucket, "").mkdir(parents=True, exist_ok=True)
        self._path(self.published_bucket, "").mkdir(parents=True, exist_ok=True)

    def presign_put(self, *, version_id: str, key: str, content_type: str) -> UploadGrant:
        expires_at = datetime.now(UTC) + timedelta(seconds=self._expires_seconds)
        payload = json.dumps(
            {
                "bucket": self.quarantine_bucket,
                "content_type": content_type,
                "exp": int(expires_at.timestamp()),
                "key": key,
                "max_bytes": self._max_bytes,
                "version_id": version_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._signing_key, payload, hashlib.sha256).digest()
        token = f"{_b64(payload)}.{_b64(signature)}"
        return UploadGrant(
            url=f"{self._public_base}/uploads/{version_id}/content?token={token}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    def receive_local_upload(self, *, token: str, content: bytes) -> tuple[str, str]:
        try:
            payload_part, signature_part = token.split(".", 1)
            payload = _unb64(payload_part)
            signature = _unb64(signature_part)
            expected = hmac.new(self._signing_key, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature mismatch")
            data = json.loads(payload)
            if int(data["exp"]) < int(datetime.now(UTC).timestamp()):
                raise ValueError("grant expired")
            if data["bucket"] != self.quarantine_bucket:
                raise ValueError("invalid bucket")
            if len(content) > int(data["max_bytes"]):
                raise ObjectStoreError("UPLOAD_TOO_LARGE", "The uploaded object is too large.")
            key = str(data["key"])
        except ObjectStoreError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ObjectStoreError("UPLOAD_GRANT_INVALID", "The upload grant is invalid.") from exc
        path = self._path(self.quarantine_bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return self.quarantine_bucket, key

    def stat(self, bucket: str, key: str) -> ObjectInfo:
        path = self._path(bucket, key)
        if not path.is_file():
            raise ObjectStoreError("OBJECT_NOT_FOUND", "The uploaded object was not found.")
        return ObjectInfo(size_bytes=path.stat().st_size, content_type=None)

    def read(self, bucket: str, key: str, *, max_bytes: int) -> bytes:
        path = self._path(bucket, key)
        if not path.is_file():
            raise ObjectStoreError("OBJECT_NOT_FOUND", "The uploaded object was not found.")
        if path.stat().st_size > max_bytes:
            raise ObjectStoreError("UPLOAD_TOO_LARGE", "The uploaded object is too large.")
        return path.read_bytes()

    def copy(
        self, source_bucket: str, source_key: str, target_bucket: str, target_key: str
    ) -> None:
        content = self.read(source_bucket, source_key, max_bytes=self._max_bytes)
        target = self._path(target_bucket, target_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def delete(self, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        if path.exists():
            path.unlink()

    def _path(self, bucket: str, key: str) -> Path:
        if bucket not in {self.quarantine_bucket, self.published_bucket}:
            raise ObjectStoreError("OBJECT_SCOPE_INVALID", "The object scope is invalid.")
        candidate = (self._root / bucket / key).resolve()
        bucket_root = (self._root / bucket).resolve()
        if candidate != bucket_root and bucket_root not in candidate.parents:
            raise ObjectStoreError("OBJECT_SCOPE_INVALID", "The object scope is invalid.")
        return candidate


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.quarantine_bucket = settings.object_store_quarantine_bucket
        self.published_bucket = settings.object_store_published_bucket
        self._region = settings.object_store_region
        self._auto_create = settings.object_store_auto_create_buckets
        self._expires_seconds = settings.upload_presign_seconds
        common = {
            "aws_access_key_id": settings.object_store_access_key,
            "aws_secret_access_key": settings.object_store_secret_key,
            "region_name": self._region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client = boto3.client("s3", endpoint_url=settings.object_store_endpoint_url, **common)
        self._public_client = boto3.client(
            "s3", endpoint_url=settings.object_store_public_endpoint_url, **common
        )

    def initialize(self) -> None:
        for bucket in (self.quarantine_bucket, self.published_bucket):
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError as exc:
                if not self._auto_create:
                    raise ObjectStoreError(
                        "OBJECT_BUCKET_UNAVAILABLE", "A required object bucket is unavailable."
                    ) from exc
                kwargs: dict[str, object] = {"Bucket": bucket}
                if self._region != "us-east-1":
                    kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
                self._client.create_bucket(**kwargs)

    def presign_put(self, *, version_id: str, key: str, content_type: str) -> UploadGrant:
        del version_id
        expires_at = datetime.now(UTC) + timedelta(seconds=self._expires_seconds)
        url = self._public_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.quarantine_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=self._expires_seconds,
            HttpMethod="PUT",
        )
        return UploadGrant(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    def receive_local_upload(self, *, token: str, content: bytes) -> tuple[str, str]:
        del token, content
        raise ObjectStoreError(
            "UPLOAD_DIRECT_REQUIRED", "This environment requires direct object-store upload."
        )

    def stat(self, bucket: str, key: str) -> ObjectInfo:
        try:
            response = self._client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            raise ObjectStoreError(
                "OBJECT_NOT_FOUND", "The uploaded object was not found."
            ) from exc
        return ObjectInfo(
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
        )

    def read(self, bucket: str, key: str, *, max_bytes: int) -> bytes:
        info = self.stat(bucket, key)
        if info.size_bytes > max_bytes:
            raise ObjectStoreError("UPLOAD_TOO_LARGE", "The uploaded object is too large.")
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            return bytes(response["Body"].read(max_bytes + 1))
        except ClientError as exc:
            raise ObjectStoreError("OBJECT_READ_FAILED", "The object could not be read.") from exc

    def copy(
        self, source_bucket: str, source_key: str, target_bucket: str, target_key: str
    ) -> None:
        try:
            self._client.copy_object(
                Bucket=target_bucket,
                Key=target_key,
                CopySource={"Bucket": source_bucket, "Key": source_key},
            )
        except ClientError as exc:
            raise ObjectStoreError(
                "OBJECT_PUBLISH_FAILED", "The validated object could not be published."
            ) from exc

    def delete(self, bucket: str, key: str) -> None:
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            raise ObjectStoreError(
                "OBJECT_DELETE_FAILED", "The object could not be deleted."
            ) from exc


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store_backend == "s3":
        return S3ObjectStore(settings)
    return LocalObjectStore(settings)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError("non-canonical base64url")
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _b64(decoded) != value:
        raise ValueError("non-canonical base64url")
    return decoded
