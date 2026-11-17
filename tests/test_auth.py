import pytest
import jwt

from app.core.config import settings


@pytest.mark.asyncio
async def test_login_wrong_credentials(async_client):
    """Wrong credentials should return 401 Unauthorized"""
    login_data = {"username": "nobody@example.test", "password": "wrong_password"}
    response = await async_client.post("/api/v1/auth/token", data=login_data)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_login_is_rate_limited(async_client):
    login_data = {"username": "nobody@example.test", "password": "wrong_password"}
    for _ in range(5):
        response = await async_client.post("/api/v1/auth/token", data=login_data)
        assert response.status_code == 401

    response = await async_client.post("/api/v1/auth/token", data=login_data)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_access_admin_route_without_token(async_client):
    """RBAC test: Anonymous user cannot access protected routes"""
    # Trying to access translations, on which you have Depends(get_admin)
    response = await async_client.get("/api/v1/localization/translations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_response_is_not_cacheable(admin_client):
    response = await admin_client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@example.com",
            "password": "secure-admin-password",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_access_token_requires_expiry_and_issued_at(admin_client):
    current_user = await admin_client.get("/api/v1/users/me")
    user_id = current_user.json()["id"]
    incomplete_token = jwt.encode(
        {"sub": user_id}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    response = await admin_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {incomplete_token}"},
    )

    assert response.status_code == 401
