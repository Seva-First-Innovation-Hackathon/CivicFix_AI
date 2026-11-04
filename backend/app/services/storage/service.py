import os
import uuid
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Tuple
try:
    from PIL import Image
except ImportError:
    Image = None
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

class StorageService:
    def __init__(self, upload_dir: str = settings.UPLOAD_DIR):
        self.upload_dir = Path(upload_dir)
        self.complaint_dir = self.upload_dir / "complaints"
        self.resolution_dir = self.upload_dir / "resolutions"
        self.evidence_dir = self.upload_dir / "evidence"
        self.complaint_dir.mkdir(parents=True, exist_ok=True)
        self.resolution_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(
        self, 
        file: UploadFile, 
        folder: str = "complaints",
        is_audio: bool = False
    ) -> Tuple[str, str, int, str]:
        """
        Validates, decodes, strips unnecessary metadata (EXIF/GPS), and safely persists uploaded file.
        Returns: (file_name, file_path_rel, file_size, mime_type)
        """
        # Read content and enforce size limit
        content = await file.read()
        file_size = len(content)
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

        if file_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
            )

        # Validate MIME type
        content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        allowed_types = settings.ALLOWED_AUDIO_TYPES if is_audio else settings.ALLOWED_IMAGE_TYPES
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type '{content_type}'. Allowed types: {', '.join(allowed_types)}"
            )

        # Sanitize extension
        original_ext = Path(file.filename or "").suffix.lower()
        if not original_ext:
            original_ext = ".jpg" if not is_audio else ".webm"
            
        safe_image_exts = [".jpg", ".jpeg", ".png", ".webp"]
        safe_audio_exts = [".mp3", ".wav", ".webm", ".ogg"]
        allowed_exts = safe_audio_exts if is_audio else safe_image_exts
        if original_ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{original_ext}'. Allowed: {', '.join(allowed_exts)}"
            )

        # Decode image and strip EXIF (GPS, device serials, camera tags) for citizen privacy
        if not is_audio:
            if Image is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Image processing subsystem (Pillow) is unavailable. Cannot securely validate or sanitize uploaded image."
                )
            try:
                # 1. Signature and structure validation
                raw_image = Image.open(BytesIO(content))
                raw_image.verify()

                # 2. Re-open to read pixels and strip metadata
                img = Image.open(BytesIO(content))
                # Convert RGBA to RGB for JPEG compatibility
                if img.mode in ("RGBA", "P") and original_ext in [".jpg", ".jpeg"]:
                    img = img.convert("RGB")
                
                # Strip all EXIF / metadata by creating fresh clean image from pixel data
                clean_img = Image.new(img.mode, img.size)
                clean_img.putdata(list(img.getdata()))

                buffer = BytesIO()
                save_fmt = "JPEG" if original_ext in [".jpg", ".jpeg"] else ("PNG" if original_ext == ".png" else "WEBP")
                clean_img.save(buffer, format=save_fmt, quality=90)
                content = buffer.getvalue()
                file_size = len(content)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image validation failed: Corrupt image file or invalid image structure."
                )

        # Generate non-colliding server-side filename (prevents directory traversal attacks)
        unique_name = f"{uuid.uuid4().hex}{original_ext}"
        if folder == "resolutions":
            target_dir = self.resolution_dir
        elif folder == "evidence":
            target_dir = self.evidence_dir
        else:
            target_dir = self.complaint_dir

        dest_path = target_dir / unique_name

        with open(dest_path, "wb") as f:
            f.write(content)

        # Relative path for internal identifier
        rel_path = f"/uploads/{folder}/{unique_name}"
        return file.filename or unique_name, rel_path, file_size, content_type

    def get_absolute_path(self, rel_path: str) -> Path:
        clean_rel = rel_path.lstrip("/").replace("uploads/", "")
        return self.upload_dir / clean_rel

storage_service = StorageService()
