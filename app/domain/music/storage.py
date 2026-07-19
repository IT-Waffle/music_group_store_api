import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import aiofiles
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings

from .models import AssetKind


@dataclass(slots=True)
class MediaMetadata:
    content_type: str
    size_bytes: int
    extension: str
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None


@dataclass(slots=True)
class StagedMedia:
    path: Path
    original_filename: str
    metadata: MediaMetadata


class MediaValidationError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class LocalMusicStorage:
    IMAGE_TYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    AUDIO_TYPES = {
        ".mp3": {"audio/mpeg", "audio/mp3"},
        ".m4a": {"audio/mp4", "audio/x-m4a", "audio/aac"},
    }
    VIDEO_TYPES = {".mp4": {"video/mp4"}}

    def __init__(self, root: Path | None = None):
        self.root = (root or settings.MUSIC_MEDIA_ROOT).resolve()
        self.temp_root = self.root / ".tmp"

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, storage_key: str) -> Path:
        pure_key = PurePosixPath(storage_key)
        if pure_key.is_absolute() or ".." in pure_key.parts:
            raise ValueError("Invalid storage key")
        resolved = (self.root / Path(*pure_key.parts)).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return resolved

    def exists(self, storage_key: str) -> bool:
        try:
            return self.resolve(storage_key).is_file()
        except ValueError:
            return False

    async def stage(self, file: UploadFile, kind: AssetKind) -> StagedMedia:
        filename = Path(file.filename or "upload").name
        extension = Path(filename).suffix.lower()
        allowed_mime, max_bytes = self._upload_rules(kind, extension)
        if file.content_type not in allowed_mime:
            raise MediaValidationError(
                415,
                "MEDIA_TYPE_UNSUPPORTED",
                f"Unsupported content type for {kind.value}.",
            )

        self.ensure_directories()
        temp_path = self.temp_root / f"{uuid.uuid4().hex}{extension}"
        size = 0
        try:
            async with aiofiles.open(temp_path, "wb") as output:
                while chunk := await file.read(settings.MUSIC_UPLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise MediaValidationError(
                            413,
                            "MEDIA_TOO_LARGE",
                            f"The {kind.value} file exceeds the configured size limit.",
                        )
                    await output.write(chunk)
            if size == 0:
                raise MediaValidationError(
                    422, "MEDIA_INVALID", "The uploaded file is empty."
                )

            metadata = await self._inspect(temp_path, kind, extension, size)
            return StagedMedia(
                path=temp_path,
                original_filename=filename[:255],
                metadata=metadata,
            )
        except Exception:
            try:
                await self.delete_path(temp_path)
            except OSError:
                pass
            raise

    async def promote(
        self, staged: StagedMedia, owner_id: uuid.UUID, kind: AssetKind
    ) -> str:
        storage_key = (
            PurePosixPath(str(owner_id))
            / kind.value
            / f"{uuid.uuid4().hex}{staged.metadata.extension}"
        ).as_posix()
        destination = self.resolve(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(os.replace, staged.path, destination)
        return storage_key

    async def delete(self, storage_key: str) -> None:
        try:
            await self.delete_path(self.resolve(storage_key))
        except ValueError:
            return

    @staticmethod
    async def delete_path(path: Path) -> None:
        await asyncio.to_thread(path.unlink, missing_ok=True)

    def _upload_rules(self, kind: AssetKind, extension: str) -> tuple[set[str], int]:
        if kind in {AssetKind.COVER, AssetKind.POSTER}:
            content_type = self.IMAGE_TYPES.get(extension)
            if not content_type:
                raise MediaValidationError(
                    415,
                    "MEDIA_TYPE_UNSUPPORTED",
                    "Only JPEG, PNG and WebP images are supported.",
                )
            return {content_type}, settings.MUSIC_IMAGE_MAX_BYTES
        if kind == AssetKind.AUDIO:
            content_types = self.AUDIO_TYPES.get(extension)
            if not content_types:
                raise MediaValidationError(
                    415,
                    "MEDIA_TYPE_UNSUPPORTED",
                    "Only MP3 and M4A audio are supported.",
                )
            return content_types, settings.MUSIC_AUDIO_MAX_BYTES
        content_types = self.VIDEO_TYPES.get(extension)
        if not content_types:
            raise MediaValidationError(
                415, "MEDIA_TYPE_UNSUPPORTED", "Only MP4 video is supported."
            )
        return content_types, settings.MUSIC_VIDEO_MAX_BYTES

    async def _inspect(
        self, path: Path, kind: AssetKind, extension: str, size: int
    ) -> MediaMetadata:
        if kind in {AssetKind.COVER, AssetKind.POSTER}:
            width, height, actual_format = await asyncio.to_thread(
                self._inspect_image, path
            )
            expected_formats = {
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".png": "PNG",
                ".webp": "WEBP",
            }
            if actual_format != expected_formats[extension]:
                raise MediaValidationError(
                    422, "MEDIA_INVALID", "Image content does not match its extension."
                )
            return MediaMetadata(
                content_type=self.IMAGE_TYPES[extension],
                size_bytes=size,
                extension=extension,
                width=width,
                height=height,
            )

        probe = await self._ffprobe(path)
        streams = probe.get("streams", [])
        duration = probe.get("format", {}).get("duration")
        try:
            duration_ms = int(float(duration) * 1000) if duration is not None else None
        except (TypeError, ValueError):
            duration_ms = None
        if duration_ms is None or duration_ms <= 0:
            raise MediaValidationError(
                422, "MEDIA_INVALID", "Media duration is invalid."
            )

        if kind == AssetKind.AUDIO:
            audio_stream = next(
                (stream for stream in streams if stream.get("codec_type") == "audio"),
                None,
            )
            allowed_codec = "mp3" if extension == ".mp3" else "aac"
            if not audio_stream or audio_stream.get("codec_name") != allowed_codec:
                raise MediaValidationError(
                    415,
                    "MEDIA_CODEC_UNSUPPORTED",
                    f"Expected {allowed_codec} audio codec.",
                )
            content_type = "audio/mpeg" if extension == ".mp3" else "audio/mp4"
            return MediaMetadata(
                content_type=content_type,
                size_bytes=size,
                extension=extension,
                duration_ms=duration_ms,
                codec=allowed_codec,
            )

        video_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "video"), None
        )
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"), None
        )
        if not video_stream or video_stream.get("codec_name") != "h264":
            raise MediaValidationError(
                415, "MEDIA_CODEC_UNSUPPORTED", "Video codec must be H.264."
            )
        if not audio_stream or audio_stream.get("codec_name") != "aac":
            raise MediaValidationError(
                415, "MEDIA_CODEC_UNSUPPORTED", "Video audio codec must be AAC."
            )
        return MediaMetadata(
            content_type="video/mp4",
            size_bytes=size,
            extension=extension,
            duration_ms=duration_ms,
            width=video_stream.get("width"),
            height=video_stream.get("height"),
            codec="h264/aac",
        )

    @staticmethod
    def _inspect_image(path: Path) -> tuple[int, int, str | None]:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                return image.width, image.height, image.format
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise MediaValidationError(
                422, "MEDIA_INVALID", "The uploaded image is invalid."
            ) from exc

    async def _ffprobe(self, path: Path) -> dict:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                settings.FFPROBE_BIN,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=settings.FFPROBE_TIMEOUT_SECONDS
            )
        except FileNotFoundError as exc:
            raise MediaValidationError(
                500, "MEDIA_INSPECTOR_UNAVAILABLE", "Media inspector is unavailable."
            ) from exc
        except TimeoutError as exc:
            if process is not None:
                process.kill()
                await process.communicate()
            raise MediaValidationError(
                422, "MEDIA_INVALID", "Media inspection timed out."
            ) from exc

        if process is None or process.returncode != 0:
            raise MediaValidationError(
                422, "MEDIA_INVALID", "The media file is invalid."
            )
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise MediaValidationError(
                422, "MEDIA_INVALID", "The media file is invalid."
            ) from exc
