from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn


class Settings(BaseSettings):
    POSTGRES_URL: PostgresDsn
    REDIS_URL: str = "redis://cache:6379"  # docker default
    ENVIRONMENT: str = "development"
    

    # AUTHENTIFICATION SECRETS
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)


settings = Settings()  # type: ignore[call-arg] Loaded from .env file
