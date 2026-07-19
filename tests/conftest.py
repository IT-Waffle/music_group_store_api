import fnmatch
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-thirty-two-bytes")
os.environ.setdefault("ENVIRONMENT", "testing")

from app.domain.catalog.models import Category, Product, ProductImage  # noqa: E402,F401
from app.domain.localization.models import Translation  # noqa: E402,F401
from app.domain.music.models import MusicAsset, MusicClip, MusicTrack  # noqa: E402,F401
from app.domain.users.models import UserRole  # noqa: E402
from app.domain.users.repository import UserRepository  # noqa: E402
from app.domain.users.schemas import UserCreate  # noqa: E402
from app.domain.users.service import UserService  # noqa: E402
from app.infrastructure.base import Base  # noqa: E402
from app.infrastructure.cache import get_redis  # noqa: E402
from app.infrastructure.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value, ex: int | None = None):
        self.data[key] = str(value)
        if ex is not None:
            self.expiries[key] = ex
        return True

    async def delete(self, *keys: str):
        removed = 0
        for key in keys:
            removed += int(key in self.data)
            self.data.pop(key, None)
            self.expiries.pop(key, None)
        return removed

    async def incr(self, key: str):
        value = int(self.data.get(key, "0")) + 1
        self.data[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int):
        self.expiries[key] = seconds
        return True

    async def ttl(self, key: str):
        return self.expiries.get(key, -1)

    async def ping(self):
        return True

    async def scan_iter(self, match: str):
        for key in list(self.data):
            if fnmatch.fnmatch(key, match):
                yield key


@pytest_asyncio.fixture
async def db_factory(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_factory) -> AsyncIterator[AsyncSession]:
    """Compatibility fixture backed by the isolated per-test database."""
    async with db_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def seed_test_data(db_factory) -> None:
    """Seed the UI translation expected by the original localization test."""
    async with db_factory() as session:
        session.add(
            Translation(
                entity_type="ui",
                entity_id="header",
                lang="en",
                key="login",
                value="Login",
            )
        )
        await session.commit()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest_asyncio.fixture
async def async_client(db_factory, fake_redis) -> AsyncIterator[AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        async with db_factory() as session:
            yield session

    async def override_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def create_user(db_factory, *, email: str, password: str, role: UserRole):
    async with db_factory() as session:
        return await UserService(UserRepository(session)).create_user(
            UserCreate(email=email, password=password, role=role)
        )


@pytest_asyncio.fixture
async def admin_client(async_client, db_factory) -> AsyncIterator[AsyncClient]:
    email = "admin@example.com"
    password = "secure-admin-password"
    await create_user(db_factory, email=email, password=password, role=UserRole.ADMIN)
    response = await async_client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    async_client.headers["Authorization"] = f"Bearer {token}"
    yield async_client


@pytest_asyncio.fixture
async def moderator_client(async_client, db_factory) -> AsyncIterator[AsyncClient]:
    email = "moderator@example.com"
    password = "secure-moderator-password"
    await create_user(
        db_factory, email=email, password=password, role=UserRole.MODERATOR
    )
    response = await async_client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    async_client.headers["Authorization"] = f"Bearer {token}"
    yield async_client
