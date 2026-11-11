from pathlib import Path

from pydantic import PostgresDsn, SecretStr, model_validator
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
    # Swagger/ReDoc/OpenAPI. None = enabled everywhere except production.
    API_DOCS_ENABLED: bool | None = None
    # Max body for non-upload requests (JSON, forms). Upload routes have their
    # own limits from the MUSIC_*_MAX_BYTES settings.
    MAX_REQUEST_BODY_BYTES: int = 1024 * 1024
    AUTH_RATE_LIMIT_ATTEMPTS: int = 5
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # Comments: max submissions per client IP per window (anti-spam)
    COMMENT_RATE_LIMIT_ATTEMPTS: int = 5
    COMMENT_RATE_LIMIT_WINDOW_SECONDS: int = 600

    # Email notification to the owner when a new comment arrives (Brevo API)
    NOTIFICATIONS_ENABLED: bool = False
    BREVO_API_KEY: SecretStr | None = None
    BREVO_API_URL: str = "https://api.brevo.com/v3/smtp/email"
    MAIL_FROM: str | None = None
    MAIL_FROM_NAME: str = "Amor Fati"
    COMMENT_NOTIFY_EMAIL: str | None = None
    NOTIFICATION_TIMEOUT_SECONDS: float = 10
    NOTIFICATION_MAX_ATTEMPTS: int = 3
    NOTIFICATION_RETRY_BACKOFF_SECONDS: float = 2

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
        if self.COMMENT_RATE_LIMIT_ATTEMPTS < 1:
            raise ValueError("COMMENT_RATE_LIMIT_ATTEMPTS must be positive")
        if self.COMMENT_RATE_LIMIT_WINDOW_SECONDS < 1:
            raise ValueError("COMMENT_RATE_LIMIT_WINDOW_SECONDS must be positive")
        if self.NOTIFICATIONS_ENABLED:
            missing = [
                name
                for name, value in (
                    ("BREVO_API_KEY", self.BREVO_API_KEY and self.BREVO_API_KEY.get_secret_value()),
                    ("MAIL_FROM", self.MAIL_FROM),
                    ("COMMENT_NOTIFY_EMAIL", self.COMMENT_NOTIFY_EMAIL),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "NOTIFICATIONS_ENABLED requires: " + ", ".join(missing)
                )
            for name in ("MAIL_FROM", "COMMENT_NOTIFY_EMAIL"):
                if "@" not in getattr(self, name):
                    raise ValueError(f"{name} must be an email address")
        if self.NOTIFICATION_MAX_ATTEMPTS < 1:
            raise ValueError("NOTIFICATION_MAX_ATTEMPTS must be positive")
        if self.NOTIFICATION_TIMEOUT_SECONDS <= 0:
            raise ValueError("NOTIFICATION_TIMEOUT_SECONDS must be positive")
        if self.MAX_REQUEST_BODY_BYTES < 1024:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be at least 1 KiB")
        if self.MUSIC_UPLOAD_CHUNK_BYTES < 64 * 1024:
            raise ValueError("MUSIC_UPLOAD_CHUNK_BYTES must be at least 64 KiB")
        return self


    @property
    def api_docs_enabled(self) -> bool:
        if self.API_DOCS_ENABLED is not None:
            return self.API_DOCS_ENABLED
        return self.ENVIRONMENT.lower() != "production"


settings = Settings()  # type: ignore[call-arg] Loaded from .env file
