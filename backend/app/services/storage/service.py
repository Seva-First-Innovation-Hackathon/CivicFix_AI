from dataclasses import dataclass
from io import BytesIO
import logging
import mimetypes
from pathlib import Path
from typing import Iterator, Optional, Tuple
import uuid

try:
    from PIL import Image
except ImportError:
    Image = None

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.storage.backends import (
    ALLOWED_STORAGE_FOLDERS,
    LocalStorageBackend,
    S3CompatibleStorageBackend,
    StorageBackend,
    StorageObjectMetadata,
    StorageObjectNotFoundError,
    StorageUnavailableError,
    compute_sha256_hex,
    normalize_object_key,
)

logger = logging.getLogger(__name__)


@dataclass
class SavedFileResult:
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    storage_provider: str
    storage_object_key: str
    sha256_checksum: str
    storage_verification_status: str = "VERIFIED"


class StorageService:
    ALLOWED_FOLDERS = ALLOWED_STORAGE_FOLDERS

    def __init__(
        self,
        upload_dir: str = settings.UPLOAD_DIR,
        cloud_backend: Optional[StorageBackend] = None,
    ):
        self._upload_dir = Path(upload_dir)
        self.complaint_dir = self._upload_dir / "complaints"
        self.resolution_dir = self._upload_dir / "resolutions"
        self.evidence_dir = self._upload_dir / "evidence"
        self._local_backend = LocalStorageBackend(self._upload_dir)
        self._cloud_backend: Optional[StorageBackend] = cloud_backend

    @property
    def upload_dir(self) -> Path:
        return self._upload_dir

    @upload_dir.setter
    def upload_dir(self, value: Path | str) -> None:
        self._upload_dir = Path(value)
        self._local_backend = LocalStorageBackend(self._upload_dir)
        self.complaint_dir = self._upload_dir / "complaints"
        self.resolution_dir = self._upload_dir / "resolutions"
        self.evidence_dir = self._upload_dir / "evidence"

    @property
    def local_backend(self) -> LocalStorageBackend:
        return self._local_backend

    def configure_cloud_backend(self, backend: Optional[StorageBackend]) -> None:
        """Sets or clears the active cloud S3/R2 storage backend (used at runtime or in tests)."""
        self._cloud_backend = backend

    def get_cloud_backend(self) -> Optional[S3CompatibleStorageBackend | StorageBackend]:
        if self._cloud_backend is not None:
            return self._cloud_backend

        backend_mode = (settings.STORAGE_BACKEND or "local").strip().lower()
        if backend_mode in {"r2", "s3"}:
            self._cloud_backend = S3CompatibleStorageBackend(
                bucket_name=settings.R2_BUCKET_NAME,
                access_key_id=settings.R2_ACCESS_KEY_ID,
                secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                endpoint_url=settings.R2_ENDPOINT_URL,
                region=settings.R2_REGION,
                provider_name=backend_mode,
            )
            return self._cloud_backend
        return None

    def get_active_backend(self) -> StorageBackend:
        backend_mode = (settings.STORAGE_BACKEND or "local").strip().lower()
        if backend_mode in {"r2", "s3"}:
            cloud = self.get_cloud_backend()
            if cloud is None:
                raise StorageUnavailableError(
                    f"Configured durable storage backend '{backend_mode}' is unavailable."
                )
            return cloud
        return self._local_backend

    def is_durable(self) -> bool:
        try:
            return bool(self.get_active_backend().is_durable)
        except Exception:
            return False

    def get_backend_for_record(self, storage_provider: Optional[str]) -> StorageBackend:
        provider = (storage_provider or "local").strip().lower()
        if provider == "local":
            return self._local_backend
        if provider in {"r2", "s3"}:
            cloud = self.get_cloud_backend()
            if cloud is not None:
                return cloud
            raise StorageUnavailableError(
                f"Evidence record stored on '{provider}', but cloud object storage client is not configured."
            )
        raise StorageUnavailableError(f"Unsupported evidence storage provider '{provider}'.")

    def ensure_local_directories(self) -> None:
        self._local_backend.ensure_directories()

    def _validate_and_sanitize_bytes(
        self,
        filename: Optional[str],
        content_type: Optional[str],
        content: bytes,
        folder: str = "complaints",
        is_audio: bool = False,
    ) -> Tuple[str, bytes, str, str]:
        if folder not in self.ALLOWED_FOLDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage folder specified",
            )

        file_size = len(content)
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded evidence file is empty",
            )
        if file_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB",
            )

        resolved_mime = content_type or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
        allowed_types = settings.ALLOWED_AUDIO_TYPES if is_audio else settings.ALLOWED_IMAGE_TYPES
        if resolved_mime not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type '{resolved_mime}'. Allowed types: {', '.join(allowed_types)}",
            )

        original_ext = Path(filename or "").suffix.lower()
        if not original_ext:
            original_ext = ".jpg" if not is_audio else ".webm"

        safe_image_exts = [".jpg", ".jpeg", ".png", ".webp"]
        safe_audio_exts = [".mp3", ".wav", ".webm", ".ogg"]
        allowed_exts = safe_audio_exts if is_audio else safe_image_exts
        if original_ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{original_ext}'. Allowed: {', '.join(allowed_exts)}",
            )

        if not is_audio:
            if Image is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Image processing subsystem (Pillow) is unavailable. Cannot securely validate or sanitize uploaded image.",
                )
            try:
                raw_image = Image.open(BytesIO(content))
                raw_image.verify()

                img = Image.open(BytesIO(content))
                if img.mode in ("RGBA", "P") and original_ext in [".jpg", ".jpeg"]:
                    img = img.convert("RGB")

                # Reconstruct clean image buffer from pixel data to strip EXIF/GPS/camera tags
                clean_img = Image.new(img.mode, img.size)
                clean_img.putdata(list(img.getdata()))

                buffer = BytesIO()
                save_fmt = (
                    "JPEG" if original_ext in [".jpg", ".jpeg"]
                    else ("PNG" if original_ext == ".png" else "WEBP")
                )
                clean_img.save(buffer, format=save_fmt, quality=90)
                content = buffer.getvalue()
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image validation failed: Corrupt image file or invalid image structure.",
                )

        return (filename or f"upload{original_ext}"), content, resolved_mime, original_ext

    async def save_file_with_metadata(
        self,
        file: UploadFile,
        folder: str = "complaints",
        is_audio: bool = False,
    ) -> SavedFileResult:
        """
        Validates MIME/extension, verifies & strips EXIF metadata via Pillow, computes SHA-256,
        generates an opaque server-side object key, and stores bytes via the configured backend.
        """
        raw_bytes = await file.read()
        clean_display_name, sanitized_bytes, mime_type, original_ext = self._validate_and_sanitize_bytes(
            filename=file.filename,
            content_type=file.content_type,
            content=raw_bytes,
            folder=folder,
            is_audio=is_audio,
        )

        unique_name = f"{uuid.uuid4().hex}{original_ext}"
        object_key = f"{folder}/{unique_name}"
        rel_path = f"/uploads/{object_key}"
        expected_checksum = compute_sha256_hex(sanitized_bytes)

        try:
            backend = self.get_active_backend()
            meta = backend.put_bytes(
                object_key=object_key,
                data=sanitized_bytes,
                content_type=mime_type,
                metadata={"original-filename": Path(clean_display_name).name[:120]},
            )
        except StorageUnavailableError as exc:
            logger.error("Failed persisting uploaded evidence key=%s: %s", object_key, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Evidence storage service is temporarily unavailable. Please retry.",
            ) from exc

        return SavedFileResult(
            file_name=Path(clean_display_name).name or unique_name,
            file_path=rel_path,
            file_size=len(sanitized_bytes),
            mime_type=mime_type,
            storage_provider=meta.storage_provider,
            storage_object_key=meta.object_key,
            sha256_checksum=meta.sha256_checksum or expected_checksum,
            storage_verification_status="VERIFIED",
        )

    async def save_file(
        self,
        file: UploadFile,
        folder: str = "complaints",
        is_audio: bool = False,
    ) -> Tuple[str, str, int, str]:
        """Backward-compatible wrapper returning (file_name, rel_path, file_size, mime_type)."""
        saved = await self.save_file_with_metadata(file=file, folder=folder, is_audio=is_audio)
        return saved.file_name, saved.file_path, saved.file_size, saved.mime_type

    def resolve_object_key(self, rel_path: str, storage_object_key: Optional[str] = None) -> str:
        raw = storage_object_key or rel_path
        try:
            return normalize_object_key(raw)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid evidence path")

    def get_absolute_path(self, rel_path: str) -> Path:
        object_key = self.resolve_object_key(rel_path)
        try:
            return self._local_backend.resolve_path(object_key)
        except PermissionError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid evidence path")

    def read_bytes(
        self,
        file_path: str,
        storage_provider: Optional[str] = None,
        storage_object_key: Optional[str] = None,
    ) -> bytes:
        object_key = self.resolve_object_key(file_path, storage_object_key)
        backend = self.get_backend_for_record(storage_provider)
        return backend.get_bytes(object_key)

    def stream_object(
        self,
        file_path: str,
        storage_provider: Optional[str] = None,
        storage_object_key: Optional[str] = None,
    ) -> Iterator[bytes]:
        object_key = self.resolve_object_key(file_path, storage_object_key)
        backend = self.get_backend_for_record(storage_provider)
        return backend.stream_chunks(object_key)

    def head_object(
        self,
        file_path: str,
        storage_provider: Optional[str] = None,
        storage_object_key: Optional[str] = None,
    ) -> Optional[StorageObjectMetadata]:
        object_key = self.resolve_object_key(file_path, storage_object_key)
        backend = self.get_backend_for_record(storage_provider)
        return backend.head_metadata(object_key)

    def generate_signed_url(
        self,
        file_path: str,
        storage_provider: Optional[str] = None,
        storage_object_key: Optional[str] = None,
        download_filename: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> str:
        object_key = self.resolve_object_key(file_path, storage_object_key)
        backend = self.get_backend_for_record(storage_provider)
        return backend.generate_signed_url(
            object_key=object_key,
            expires_in=expires_in or settings.STORAGE_PRESIGNED_TTL_SECONDS,
            download_filename=download_filename,
        )


storage_service = StorageService()
