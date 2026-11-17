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


def test_rejects_unapproved_jwt_algorithm():
    with pytest.raises(ValidationError):
        Settings(
            POSTGRES_URL=PostgresDsn(
                "postgresql+asyncpg://postgres:postgres@localhost/test"
            ),
            SECRET_KEY="a-secure-secret-key-that-is-long-enough",
            ALGORITHM="none",
        )
