import pytest

from app.domain.localization.models import Translation


@pytest.mark.asyncio
async def test_get_flat_localization(async_client, db_factory):
    """Checking that DB/cache gives data"""
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
    response = await async_client.get("/api/v1/localization/flat/ui/header")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
