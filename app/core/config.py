from pathlib import Path

from pydantic import PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_URL: PostgresDsn
    REDIS_URL: str = "redis://cache:6379"  # docker default
    ENVIRONMENT: str = "development"

    # Authentication
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    CORS_ALLOWED_ORIGINS: list[str] = []
    AUTH_RATE_LIMIT_ATTEMPTS: int = 5
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # Music media
    MUSIC_MEDIA_ROOT: Path = Path("uploads/music")
    MUSIC_MEDIA_BASE_URL: str = "/api/v1/music"
    MUSIC_IMAGE_MAX_BYTES: int = 10 * 1024 * 1024
    MUSIC_AUDIO_MAX_BYTES: int = 100 * 1024 * 1024
    MUSIC_VIDEO_MAX_BYTES: int = 500 * 1024 * 1024
    MUSIC_UPLOAD_CHUNK_BYTES: int = 1024 * 1024
    FFPROBE_BIN: str = "ffprobe"
    FFPROBE_TIMEOUT_SECONDS: int = 15

    # In production Nginx serves files from an internal location after the API
    # has checked publication/authorization.
    MEDIA_USE_X_ACCEL_REDIRECT: bool = False
    MEDIA_X_ACCEL_PREFIX: str = "/_protected_music_media"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            weak_values = {
                "secret",
                "secret_key",
                "secret_key_for_local_development_only",
                "change-me",
            }
            if len(self.SECRET_KEY.encode("utf-8")) < 32 or self.SECRET_KEY in weak_values:
                raise ValueError(
                    "Production SECRET_KEY must contain at least 32 bytes of random data"
                )

        if self.AUTH_RATE_LIMIT_ATTEMPTS < 1:
            raise ValueError("AUTH_RATE_LIMIT_ATTEMPTS must be positive")
        if self.AUTH_RATE_LIMIT_WINDOW_SECONDS < 1:
            raise ValueError("AUTH_RATE_LIMIT_WINDOW_SECONDS must be positive")
        if self.MUSIC_UPLOAD_CHUNK_BYTES < 64 * 1024:
            raise ValueError("MUSIC_UPLOAD_CHUNK_BYTES must be at least 64 KiB")
        return self


settings = Settings()  # type: ignore[call-arg] Loaded from .env file
