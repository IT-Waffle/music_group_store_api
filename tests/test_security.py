import uuid

import pytest

from app.core import security
from app.core.config import Settings, settings
from app.domain.localization.models import Translation
from app.domain.users import service as user_service
from app.infrastructure.cache import get_redis
from app.main import app
from tests.test_engagement import create_product

UPLOAD_URL = f"/api/v1/music/manage/tracks/{uuid.uuid4()}/audio"


# ---- request body limits --------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_upload_is_rejected_before_body_is_read(async_client):
    huge = str(500 * 1024 * 1024)  # declared 500 MB, never actually sent
    response = await async_client.post(
        UPLOAD_URL,
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": huge},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

    forged = await async_client.post(
        UPLOAD_URL,
        content=b"x",
        headers={"authorization": "Bearer not-a-jwt"},
    )
    assert forged.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_upload_over_limit_is_413(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "MUSIC_AUDIO_MAX_BYTES", 1024)
    response = await admin_client.post(
        UPLOAD_URL,
        content=b"x",
        headers={
            "content-type": "multipart/form-data; boundary=x",
            "content-length": str(10 * 1024 * 1024),
        },
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.asyncio
async def test_large_json_body_is_rejected(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 4096)
    url = f"/api/v1/engagement/product/{uuid.uuid4()}/comments"
    payload = b'{"author_name": "a", "body": "' + b"x" * 10_000 + b'"}'

    declared = await async_client.post(
        url, content=payload, headers={"content-type": "application/json"}
    )
    assert declared.status_code == 413

    async def chunked():  # no Content-Length: counted while streaming
        for start in range(0, len(payload), 1000):
            yield payload[start : start + 1000]

    streamed = await async_client.post(
        url, content=chunked(), headers={"content-type": "application/json"}
    )
    assert streamed.status_code == 413
    assert streamed.json()["detail"]["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.asyncio
async def test_normal_requests_still_pass(admin_client):
    product_id = await create_product(admin_client, is_published=True)
    response = await admin_client.post(
        f"/api/v1/engagement/product/{product_id}/comments",
        json={"author_name": "Anna", "body": "Labi"},
    )
    assert response.status_code == 202


# ---- localization ---------------------------------------------------------


@pytest.mark.asyncio
async def test_public_localization_hides_content_texts(async_client, db_factory, fake_redis):
    async with db_factory() as session:
        session.add(
            Translation(
                entity_type="music_track",
                entity_id=str(uuid.uuid4()),
                lang="en",
                key="title",
                value="Unreleased draft",
            )
        )
        await session.commit()

    for entity_type in ("product", "music_track", "music_clip"):
        bundle = await async_client.get(f"/api/v1/localization/bundle/{entity_type}")
        assert bundle.status_code == 404
        flat = await async_client.get(f"/api/v1/localization/flat/{entity_type}/x")
        assert flat.status_code == 404

    ui = await async_client.get("/api/v1/localization/flat/ui/header")
    assert ui.json() == {"login": "Login"}

    # Unknown ids give {} and are not cached (no Redis flooding).
    for _ in range(3):
        empty = await async_client.get(f"/api/v1/localization/flat/ui/{uuid.uuid4()}")
        assert empty.json() == {}
    loc_keys = [key for key in fake_redis.data if key.startswith("loc:")]
    assert loc_keys == ["loc:flat:en:ui:header"]


@pytest.mark.asyncio
async def test_translation_by_id_requires_moderator(async_client):
    response = await async_client.get(f"/api/v1/localization/translations/{uuid.uuid4()}")
    assert response.status_code == 401


# ---- auth / users ---------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_email_still_runs_password_check(async_client, monkeypatch):
    calls = []
    monkeypatch.setattr(user_service, "burn_password_check", lambda pw: calls.append(pw))
    response = await async_client.post(
        "/api/v1/auth/token", data={"username": "nobody@example.com", "password": "guess"}
    )
    assert response.status_code == 401
    assert calls == ["guess"]


def test_dummy_hash_is_a_real_argon2_check():
    # Must not raise and must take the normal verify path.
    security.burn_password_check("anything")


@pytest.mark.asyncio
async def test_user_email_longer_than_column_is_422(admin_client):
    response = await admin_client.post(
        "/api/v1/users/",
        json={
            "email": "a" * 45 + "@example.com",
            "password": "long-enough-password",
            "role": "moderator",
        },
    )
    assert response.status_code == 422


# ---- system ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_does_not_leak_error_details(async_client):
    class BrokenRedis:
        async def ping(self):
            raise RuntimeError("redis://secret-host:6379 connection refused")

    app.dependency_overrides[get_redis] = lambda: BrokenRedis()
    response = await async_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["errors"] == {"redis": "unavailable"}
    assert "secret-host" not in response.text


def test_api_docs_are_off_in_production_by_default():
    base = {"POSTGRES_URL": "postgresql+asyncpg://u:p@localhost/db", "_env_file": None}
    production = Settings(**base, ENVIRONMENT="production", SECRET_KEY="k" * 40)
    assert production.api_docs_enabled is False
    forced = Settings(
        **base, ENVIRONMENT="production", SECRET_KEY="k" * 40, API_DOCS_ENABLED=True
    )
    assert forced.api_docs_enabled is True
    development = Settings(**base, SECRET_KEY="dev")
    assert development.api_docs_enabled is True
