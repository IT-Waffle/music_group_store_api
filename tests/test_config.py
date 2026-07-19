import pytest
from pydantic import PostgresDsn, ValidationError

from app.core.config import Settings


def test_production_rejects_weak_secret():
    with pytest.raises(ValidationError):
        Settings(
            POSTGRES_URL=PostgresDsn(
                "postgresql+asyncpg://postgres:postgres@localhost/test"
            ),
            REDIS_URL="redis://localhost:6379",
            SECRET_KEY="short",
            ENVIRONMENT="production",
        )
