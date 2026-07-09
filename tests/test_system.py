import pytest


@pytest.mark.asyncio
async def test_health_live(async_client):
    """Smoke-test: application starts"""
    response = await async_client.get("/health/live")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_ready(async_client):
    """Smoke-test: DB and Redis are connected and ready for work"""
    response = await async_client.get("/health/ready")
    assert response.status_code == 200
