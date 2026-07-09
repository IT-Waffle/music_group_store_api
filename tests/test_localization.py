import pytest


@pytest.mark.asyncio
async def test_get_flat_localization(async_client):
    """Checking that DB/cache gives data"""
    response = await async_client.get("/api/v1/localization/flat/ui/header")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
