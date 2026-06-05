from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn


class Settings(BaseSettings):
    # TODO: Change logic to creating url here instead of getting ready one in future
    # POSTGRES_USER: str
    # POSTRGES_PASSWORD: str
    # POSTGRES_NAME: str
    POSTGRES_URL: PostgresDsn

    # AUTHENTIFICATION SECRETS
    SECRET_KEY: str
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore[call-arg] Loaded from .env file
