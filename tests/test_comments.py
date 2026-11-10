import uuid

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app.core.config import settings
from app.domain.engagement.models import Comment
from app.infrastructure.cache import get_redis
from app.main import app
from app.domain.music.storage import LocalMusicStorage
from tests.test_engagement import create_product
from tests.test_music import fake_ffprobe, translations


def comments_url(target_type: str, target_id: str) -> str:
    return f"/api/v1/engagement/{target_type}/{target_id}/comments"


async def submit(client, target_id: str, **overrides):
    payload = {"author_name": "Jānis", "body": "Skaista glezna!", **overrides}
    return await client.post(comments_url("product", target_id), json=payload)


async def count_comments(db_factory) -> int:
    async with db_factory() as session:
        return int(await session.scalar(select(func.count(Comment.id))))


@pytest.mark.asyncio
async def test_comment_lifecycle_pending_approve_delete(admin_client):
    product_id = await create_product(admin_client, is_published=True)

    submitted = await submit(admin_client, product_id)
    assert submitted.status_code == 202, submitted.text
    assert submitted.json() == {
        "status": "pending",
        "message": "Your comment has been sent for moderation.",
    }

    # Pending comments are never public.
    public = await admin_client.get(comments_url("product", product_id))
    assert public.status_code == 200
    assert public.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}

    queue = await admin_client.get(
        "/api/v1/engagement/manage/comments", headers={"Accept-Language": "lv"}
    )
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    item = queue.json()["items"][0]
    assert item["status"] == "pending"
    assert item["target_type"] == "product"
    assert item["target_id"] == product_id
    assert item["target_title"] == "Glezna"
    assert item["author_name"] == "Jānis"
    assert item["created_at"]
    assert item["approved_at"] is None

    approved = await admin_client.post(
        f"/api/v1/engagement/manage/comments/{item['id']}/approve"
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    first_approved_at = approved.json()["approved_at"]
    assert first_approved_at

    again = await admin_client.post(
        f"/api/v1/engagement/manage/comments/{item['id']}/approve"
    )
    assert again.status_code == 200
    assert again.json()["approved_at"] == first_approved_at

    public = (await admin_client.get(comments_url("product", product_id))).json()
    assert public["total"] == 1
    assert public["items"][0] == {
        "id": item["id"],
        "author_name": "Jānis",
        "body": "Skaista glezna!",
        "created_at": item["created_at"],
    }

    pending_queue = (await admin_client.get("/api/v1/engagement/manage/comments")).json()
    assert pending_queue["total"] == 0
    approved_queue = (
        await admin_client.get("/api/v1/engagement/manage/comments?status=approved")
    ).json()
    assert approved_queue["total"] == 1

    deleted = await admin_client.delete(f"/api/v1/engagement/manage/comments/{item['id']}")
    assert deleted.status_code == 204
    assert (await admin_client.get(comments_url("product", product_id))).json()["total"] == 0
    missing = await admin_client.delete(f"/api/v1/engagement/manage/comments/{item['id']}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "COMMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_moderation_requires_moderator_or_admin(async_client, db_factory):
    queue = await async_client.get("/api/v1/engagement/manage/comments")
    assert queue.status_code == 401
    approve = await async_client.post(
        f"/api/v1/engagement/manage/comments/{uuid.uuid4()}/approve"
    )
    assert approve.status_code == 401
    delete = await async_client.delete(f"/api/v1/engagement/manage/comments/{uuid.uuid4()}")
    assert delete.status_code == 401


@pytest.mark.asyncio
async def test_moderator_can_approve_and_delete(moderator_client):
    product_id = await create_product(moderator_client, is_published=True)
    await submit(moderator_client, product_id)
    await submit(moderator_client, product_id, author_name="Anna")
    queue = (await moderator_client.get("/api/v1/engagement/manage/comments")).json()
    assert queue["total"] == 2
    first, second = (item["id"] for item in queue["items"])

    approve = await moderator_client.post(f"/api/v1/engagement/manage/comments/{first}/approve")
    assert approve.status_code == 200
    delete = await moderator_client.delete(f"/api/v1/engagement/manage/comments/{second}")
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_comments_only_on_public_content(admin_client):
    draft_id = await create_product(admin_client, is_published=False)
    hidden_post = await submit(admin_client, draft_id)
    assert hidden_post.status_code == 404
    assert hidden_post.json()["detail"]["code"] == "CONTENT_NOT_FOUND"
    hidden_get = await admin_client.get(comments_url("product", draft_id))
    assert hidden_get.status_code == 404

    unknown = await admin_client.post(
        comments_url("music_clip", str(uuid.uuid4())),
        json={"author_name": "A", "body": "B"},
    )
    assert unknown.status_code == 404
    bad_type = await admin_client.get(comments_url("category", str(uuid.uuid4())))
    assert bad_type.status_code == 422


@pytest.mark.asyncio
async def test_comment_input_is_validated_and_cleaned(admin_client):
    product_id = await create_product(admin_client, is_published=True)

    for payload in (
        {"author_name": "   ", "body": "text"},
        {"author_name": "Name", "body": " \n\t "},
        {"author_name": "N" * 81, "body": "text"},
        {"author_name": "Name", "body": "x" * 2001},
        {"author_name": "Name", "body": "text", "email": "spam@example.com"},
    ):
        response = await admin_client.post(comments_url("product", product_id), json=payload)
        assert response.status_code == 422, payload

    ok = await submit(
        admin_client,
        product_id,
        author_name="  Anna\n‮Kalniņa​ ",
        body="  Pirmā rinda\r\n\r\n\r\n\r\nOtrā​ rinda <script>alert(1)</script>  ",
    )
    assert ok.status_code == 202, ok.text
    item = (await admin_client.get("/api/v1/engagement/manage/comments")).json()["items"][0]
    assert item["author_name"] == "Anna Kalniņa"
    # Text is stored as-is (no HTML stripping): the API returns plain text and
    # clients must render it as text, never as HTML.
    assert item["body"] == "Pirmā rinda\n\nOtrā rinda <script>alert(1)</script>"


@pytest.mark.asyncio
async def test_honeypot_is_silently_discarded(admin_client, db_factory):
    product_id = await create_product(admin_client, is_published=True)
    trapped = await submit(admin_client, product_id, website="http://spam.example")
    assert trapped.status_code == 202
    assert trapped.json()["status"] == "pending"
    assert await count_comments(db_factory) == 0


@pytest.mark.asyncio
async def test_comment_submissions_are_rate_limited(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "COMMENT_RATE_LIMIT_ATTEMPTS", 3)
    product_id = await create_product(admin_client, is_published=True)
    for _ in range(3):
        assert (await submit(admin_client, product_id)).status_code == 202
    limited = await submit(admin_client, product_id)
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_comment_accepted_when_redis_is_down(admin_client, db_factory):
    class BrokenRedis:
        async def incr(self, key):
            raise RedisConnectionError("redis is down")

    product_id = await create_product(admin_client, is_published=True)
    app.dependency_overrides[get_redis] = lambda: BrokenRedis()
    response = await submit(admin_client, product_id)
    assert response.status_code == 202
    assert await count_comments(db_factory) == 1


@pytest.mark.asyncio
async def test_deleting_content_removes_its_comments(admin_client, db_factory):
    product_id = await create_product(admin_client, is_published=True)
    await submit(admin_client, product_id)
    assert await count_comments(db_factory) == 1
    deleted = await admin_client.delete(f"/api/v1/catalog/products/{product_id}")
    assert deleted.status_code == 204
    assert await count_comments(db_factory) == 0


@pytest.mark.asyncio
async def test_track_comment_title_in_requested_language(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MUSIC_MEDIA_ROOT", tmp_path / "music")
    monkeypatch.setattr(LocalMusicStorage, "_ffprobe", fake_ffprobe)
    track = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={"slug": "commented-track", "translations": translations("Song")},
    )
    track_id = track.json()["id"]
    await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"fake-mp3", "audio/mpeg")},
    )
    assert (await admin_client.post(f"/api/v1/music/manage/tracks/{track_id}/publish")).status_code == 200

    response = await admin_client.post(
        comments_url("music_track", track_id), json={"author_name": "Ilze", "body": "Super!"}
    )
    assert response.status_code == 202, response.text
    for language, expected in (("lv", "Song LV"), ("ru", "Song RU"), ("de", "Song EN")):
        queue = await admin_client.get(
            "/api/v1/engagement/manage/comments?target_type=music_track",
            headers={"Accept-Language": language},
        )
        assert queue.json()["items"][0]["target_title"] == expected
