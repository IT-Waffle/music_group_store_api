import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.domain.localization.models import Translation
from app.main import app
from sqlalchemy import select
from app.infrastructure.session import async_session_factory


@pytest_asyncio.fixture(scope="session")
async def db_session():
    """Создает сессию для тестов, которая откатывается после каждого теста"""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


# 1. Anonymous client (pretends to be a regular visitor)
@pytest.fixture
async def async_client():
    """Anonymous client (pretends to be a regular visitor)"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


# 2. Authorized client (Admin)
@pytest.fixture
async def admin_client(async_client):
    """
    Client that logs in as an admin from seed.py
    and automatically attaches the JWT token to all subsequent requests.
    """
    login_data = {"username": "admin@band.com", "password": "admin123"}

    response = await async_client.post("/api/v1/auth/token", data=login_data)
    assert response.status_code == 200, f"Ошибка логина в тестах: {response.text}"

    token = response.json()["access_token"]

    # Creating a new client with token
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers=headers
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_test_data():
    """Создает тестовые данные в БД один раз на сессию тестов"""
    async with async_session_factory() as session:
        # Проверяем, есть ли уже тестовые переводы
        stmt = select(Translation).where(Translation.entity_type == "ui")
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            # Создаем тестовую запись: GET /localization/flat/ui/header
            test_trans = Translation(
                entity_type="ui",
                entity_id="header",
                lang="en",
                key="login",
                value="Login",
            )
            session.add(test_trans)
            await session.commit()
            print("\n🌱 Test localization seeded!")
