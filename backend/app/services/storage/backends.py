from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Dict, Iterator, Optional

logger = logging.getLogger(__name__)

ALLOWED_STORAGE_FOLDERS = {"complaints", "resolutions", "evidence"}


class StorageError(Exception):
    """Base error raised by storage backends."""


class StorageObjectNotFoundError(StorageError):
    """Raised when an expected evidence object does not exist in storage."""


class StorageUnavailableError(StorageError):
    """Raised when a configured object storage backend is unreachable or failing."""


@dataclass
class StorageObjectMetadata:
    object_key: str
    storage_provider: str
    size_bytes: int
    sha256_checksum: Optional[str]
    content_type: Optional[str] = None
    exists: bool = True


def normalize_object_key(raw_key: str) -> str:
    """
    Validates and normalizes a storage object key (<folder>/<filename>) against traversal tricks.
    Accepts '/uploads/<folder>/<filename>' or '<folder>/<filename>'.
    """
    if not raw_key or "\\" in raw_key:
        raise ValueError("Invalid evidence path")
    normalized = raw_key.strip().lstrip("/")
    if normalized.startswith("uploads/"):
        normalized = normalized[len("uploads/"):]
    parts = Path(normalized).parts
    if len(parts) != 2 or parts[0] not in ALLOWED_STORAGE_FOLDERS or ".." in parts:
        raise ValueError("Invalid evidence path")
    if not parts[1] or parts[1].startswith("."):
        raise ValueError("Invalid evidence filename")
    return f"{parts[0]}/{parts[1]}"


def compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageBackend(ABC):
    """Abstract durable/local evidence storage interface."""

    provider_name: str
    is_durable: bool = False

    @abstractmethod
    def put_bytes(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, object_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def stream_chunks(self, object_key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, object_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def head_metadata(self, object_key: str) -> Optional[StorageObjectMetadata]:
        raise NotImplementedError

    def generate_signed_url(
        self,
        object_key: str,
        expires_in: int = 300,
        download_filename: Optional[str] = None,
    ) -> str:
        raise NotImplementedError(
            f"Storage backend '{self.provider_name}' does not issue pre-signed object URLs."
        )


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend intended for development and isolated automated tests."""

    provider_name = "local"
    is_durable = False

    def __init__(self, upload_dir: Path | str):
        self.root_dir = Path(upload_dir)

    def ensure_directories(self) -> None:
        for folder in ALLOWED_STORAGE_FOLDERS:
            (self.root_dir / folder).mkdir(parents=True, exist_ok=True)

    def resolve_path(self, object_key: str) -> Path:
        clean_key = normalize_object_key(object_key)
        folder, filename = clean_key.split("/", 1)
        base_resolved = self.root_dir.resolve()
        candidate = (base_resolved / folder / filename).resolve()
        if not candidate.is_relative_to(base_resolved):
            raise PermissionError("Path traversal outside configured upload root rejected")
        return candidate

    def put_bytes(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        dest = self.resolve_path(object_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        checksum = compute_sha256_hex(data)
        with open(dest, "wb") as fh:
            fh.write(data)
        return StorageObjectMetadata(
            object_key=normalize_object_key(object_key),
            storage_provider=self.provider_name,
            size_bytes=len(data),
            sha256_checksum=checksum,
            content_type=content_type,
            exists=True,
        )

    def get_bytes(self, object_key: str) -> bytes:
        path = self.resolve_path(object_key)
        if not path.is_file():
            raise StorageObjectNotFoundError(f"Local evidence object not found: {object_key}")
        return path.read_bytes()

    def stream_chunks(self, object_key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        path = self.resolve_path(object_key)
        if not path.is_file():
            raise StorageObjectNotFoundError(f"Local evidence object not found: {object_key}")

        def _gen() -> Iterator[bytes]:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return _gen()

    def delete(self, object_key: str) -> bool:
        path = self.resolve_path(object_key)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def exists(self, object_key: str) -> bool:
        path = self.resolve_path(object_key)
        return path.is_file()

    def head_metadata(self, object_key: str) -> Optional[StorageObjectMetadata]:
        path = self.resolve_path(object_key)
        if not path.is_file():
            return None
        data = path.read_bytes()
        return StorageObjectMetadata(
            object_key=normalize_object_key(object_key),
            storage_provider=self.provider_name,
            size_bytes=len(data),
            sha256_checksum=compute_sha256_hex(data),
            content_type=None,
            exists=True,
        )


class S3CompatibleStorageBackend(StorageBackend):
    """
    Private Cloudflare R2 / S3-compatible object storage backend.
    All objects are uploaded strictly private; browser downloads must pass through
    authenticated CivicFix RBAC checks or backend-authorized short-lived signed URLs.
    """

    is_durable = True

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str,
        region: str = "auto",
        provider_name: str = "r2",
        client=None,
    ):
        self.provider_name = provider_name
        self.bucket_name = bucket_name
        self.region = region or "auto"
        self.endpoint_url = endpoint_url

        if client is not None:
            self._client = client
        else:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=self.region,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=5,
                    read_timeout=15,
                    retries={"max_attempts": 2, "mode": "standard"},
                    s3={"addressing_style": "path"},
                ),
            )

    @staticmethod
    def _is_not_found_error(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return False
        err = response.get("Error", {})
        code = str(err.get("Code", ""))
        http_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in {"404", "NoSuchKey", "NotFound"} or http_code == 404

    def put_bytes(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        clean_key = normalize_object_key(object_key)
        checksum = compute_sha256_hex(data)
        obj_meta = {"sha256": checksum}
        if metadata:
            for k, v in metadata.items():
                if v is not None:
                    obj_meta[str(k).lower()] = str(v)

        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
                Metadata=obj_meta,
            )
        except Exception as exc:
            logger.error("Object storage put_object failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Durable object storage upload failed") from exc

        return StorageObjectMetadata(
            object_key=clean_key,
            storage_provider=self.provider_name,
            size_bytes=len(data),
            sha256_checksum=checksum,
            content_type=content_type,
            exists=True,
        )

    def get_bytes(self, object_key: str) -> bytes:
        clean_key = normalize_object_key(object_key)
        try:
            resp = self._client.get_object(Bucket=self.bucket_name, Key=clean_key)
            body = resp["Body"]
            data = body.read()
            if hasattr(body, "close"):
                body.close()
            return data
        except Exception as exc:
            if self._is_not_found_error(exc):
                raise StorageObjectNotFoundError(f"Object not found in {self.provider_name}: {clean_key}") from exc
            logger.error("Object storage get_object failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Durable object storage read failed") from exc

    def stream_chunks(self, object_key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        clean_key = normalize_object_key(object_key)
        try:
            resp = self._client.get_object(Bucket=self.bucket_name, Key=clean_key)
        except Exception as exc:
            if self._is_not_found_error(exc):
                raise StorageObjectNotFoundError(f"Object not found in {self.provider_name}: {clean_key}") from exc
            logger.error("Object storage stream open failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Durable object storage stream failed") from exc

        body = resp["Body"]

        def _gen() -> Iterator[bytes]:
            try:
                if hasattr(body, "iter_chunks"):
                    for chunk in body.iter_chunks(chunk_size=chunk_size):
                        if chunk:
                            yield chunk
                else:
                    while True:
                        chunk = body.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            finally:
                if hasattr(body, "close"):
                    body.close()

        return _gen()

    def delete(self, object_key: str) -> bool:
        clean_key = normalize_object_key(object_key)
        try:
            if not self.exists(clean_key):
                return False
            self._client.delete_object(Bucket=self.bucket_name, Key=clean_key)
            return True
        except Exception as exc:
            if self._is_not_found_error(exc):
                return False
            logger.error("Object storage delete failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Durable object storage delete failed") from exc

    def exists(self, object_key: str) -> bool:
        return self.head_metadata(object_key) is not None

    def head_metadata(self, object_key: str) -> Optional[StorageObjectMetadata]:
        clean_key = normalize_object_key(object_key)
        try:
            resp = self._client.head_object(Bucket=self.bucket_name, Key=clean_key)
            meta = resp.get("Metadata") or {}
            return StorageObjectMetadata(
                object_key=clean_key,
                storage_provider=self.provider_name,
                size_bytes=int(resp.get("ContentLength", 0)),
                sha256_checksum=meta.get("sha256"),
                content_type=resp.get("ContentType"),
                exists=True,
            )
        except Exception as exc:
            if self._is_not_found_error(exc):
                return None
            logger.error("Object storage head_object failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Durable object storage metadata check failed") from exc

    def generate_signed_url(
        self,
        object_key: str,
        expires_in: int = 300,
        download_filename: Optional[str] = None,
    ) -> str:
        clean_key = normalize_object_key(object_key)
        ttl = max(10, min(int(expires_in), 3600))
        params = {"Bucket": self.bucket_name, "Key": clean_key}
        if download_filename:
            safe_name = Path(download_filename).name.replace('"', "")
            params["ResponseContentDisposition"] = f'inline; filename="{safe_name}"'
        try:
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=ttl,
            )
        except Exception as exc:
            logger.error("Presigned URL generation failed for key=%s: %s", clean_key, exc)
            raise StorageUnavailableError("Unable to issue presigned download URL") from exc
