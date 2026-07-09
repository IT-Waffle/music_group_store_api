import pytest


@pytest.mark.asyncio
async def test_login_wrong_credentials(async_client):
    """Wrong credentials should return 401 Unauthorized"""
    login_data = {"username": "admin@band.com", "password": "wrong_password"}
    response = await async_client.post("/api/v1/auth/token", data=login_data)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_access_admin_route_without_token(async_client):
    """RBAC test: Anonymous user cannot access protected routes"""
    # Trying to access translations, on which you have Depends(get_admin)
    response = await async_client.get("/api/v1/localization/translations")
    assert response.status_code == 401
