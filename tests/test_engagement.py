import uuid

import pytest

from app.core.config import settings
from app.domain.music.storage import LocalMusicStorage
from tests.test_music import fake_ffprobe, translations


async def create_product(client, *, is_published: bool) -> str:
    category = await client.post(
        "/api/v1/catalog/categories",
        json={
            "slug": f"views-category-{uuid.uuid4().hex[:8]}",
            "title_en": "Paintings",
            "title_lv": "Gleznas",
            "title_ru": "Картины",
        },
    )
    assert category.status_code == 201, category.text
    product = await client.post(
        "/api/v1/catalog/products",
        json={
            "slug": f"views-product-{uuid.uuid4().hex[:8]}",
            "category_id": category.json()["id"],
            "is_published": is_published,
            "title_en": "Painting",
            "title_lv": "Glezna",
            "title_ru": "Картина",
            "description_en": "Oil",
            "description_lv": "Eļļa",
            "description_ru": "Масло",
        },
    )
    assert product.status_code == 201, product.text
    assert product.json()["view_count"] == 0
    return product.json()["id"]


async def view(client, target_type: str, target_id: str):
    return await client.post(f"/api/v1/engagement/{target_type}/{target_id}/views")


@pytest.mark.asyncio
async def test_product_views_are_counted_and_exposed(admin_client):
    product_id = await create_product(admin_client, is_published=True)

    first = await view(admin_client, "product", product_id)
    second = await view(admin_client, "product", product_id)
    assert first.status_code == 200, first.text
    # Non-unique: the same client viewing twice counts twice.
    assert first.json() == {"view_count": 1}
    assert second.json() == {"view_count": 2}

    public_list = await admin_client.get("/api/v1/catalog/products")
    by_id = {item["id"]: item for item in public_list.json()}
    assert by_id[product_id]["view_count"] == 2

    public_detail = await admin_client.get(f"/api/v1/catalog/products/{product_id}")
    assert public_detail.json()["view_count"] == 2

    admin_detail = await admin_client.get(
        f"/api/v1/catalog/manage/products/{product_id}"
    )
    assert admin_detail.json()["view_count"] == 2


@pytest.mark.asyncio
async def test_views_rejected_for_hidden_or_unknown_content(admin_client):
    draft_id = await create_product(admin_client, is_published=False)

    hidden = await view(admin_client, "product", draft_id)
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "CONTENT_NOT_FOUND"

    missing = await view(admin_client, "music_track", str(uuid.uuid4()))
    assert missing.status_code == 404

    bad_type = await view(admin_client, "category", str(uuid.uuid4()))
    assert bad_type.status_code == 422

    # A rejected view must not leave a counter behind.
    admin_detail = await admin_client.get(f"/api/v1/catalog/manage/products/{draft_id}")
    assert admin_detail.json()["view_count"] == 0


@pytest.mark.asyncio
async def test_track_and_clip_views(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MUSIC_MEDIA_ROOT", tmp_path / "music")
    monkeypatch.setattr(LocalMusicStorage, "_ffprobe", fake_ffprobe)

    track = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={"slug": "viewed-track", "translations": translations("Viewed")},
    )
    assert track.status_code == 201, track.text
    track_id = track.json()["id"]
    assert track.json()["view_count"] == 0

    audio = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"fake-mp3", "audio/mpeg")},
    )
    assert audio.status_code == 200, audio.text

    clip = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/clips",
        json={"translations": translations("Viewed clip")},
    )
    assert clip.status_code == 201, clip.text
    clip_id = clip.json()["id"]
    video = await admin_client.post(
        f"/api/v1/music/manage/clips/{clip_id}/video",
        files={"file": ("clip.mp4", b"fake-mp4", "video/mp4")},
    )
    assert video.status_code == 200, video.text

    # Draft track and unpublished clip are not public yet.
    assert (await view(admin_client, "music_track", track_id)).status_code == 404
    assert (await view(admin_client, "music_clip", clip_id)).status_code == 404

    published_clip = await admin_client.patch(
        f"/api/v1/music/manage/tracks/{track_id}/clips/{clip_id}",
        json={"is_published": True},
    )
    assert published_clip.status_code == 200, published_clip.text
    published = await admin_client.post(f"/api/v1/music/manage/tracks/{track_id}/publish")
    assert published.status_code == 200, published.text

    assert (await view(admin_client, "music_track", track_id)).json() == {"view_count": 1}
    await view(admin_client, "music_clip", clip_id)
    assert (await view(admin_client, "music_clip", clip_id)).json() == {"view_count": 2}

    public_list = (await admin_client.get("/api/v1/music/tracks")).json()["items"][0]
    assert public_list["view_count"] == 1
    assert public_list["clips"][0]["view_count"] == 2

    public_detail = (await admin_client.get("/api/v1/music/tracks/viewed-track")).json()
    assert public_detail["view_count"] == 1
    assert public_detail["clips"][0]["view_count"] == 2

    clip_list = (await admin_client.get("/api/v1/music/clips")).json()["items"][0]
    assert clip_list["view_count"] == 2
    clip_detail = (await admin_client.get(f"/api/v1/music/clips/{clip_id}")).json()
    assert clip_detail["view_count"] == 2

    admin_detail = (
        await admin_client.get(f"/api/v1/music/manage/tracks/{track_id}")
    ).json()
    assert admin_detail["view_count"] == 1
    assert admin_detail["clips"][0]["view_count"] == 2
    admin_list = (await admin_client.get("/api/v1/music/manage/tracks")).json()
    assert admin_list["items"][0]["view_count"] == 1

    # Unpublishing hides the track again; its counter is kept, not reset.
    await admin_client.post(f"/api/v1/music/manage/tracks/{track_id}/unpublish")
    assert (await view(admin_client, "music_track", track_id)).status_code == 404
    admin_after = (
        await admin_client.get(f"/api/v1/music/manage/tracks/{track_id}")
    ).json()
    assert admin_after["view_count"] == 1


@pytest.mark.asyncio
async def test_deleting_content_removes_its_counter(admin_client, db_factory):
    from sqlalchemy import func, select

    from app.domain.engagement.models import ViewCounter

    product_id = await create_product(admin_client, is_published=True)
    await view(admin_client, "product", product_id)

    deleted = await admin_client.delete(f"/api/v1/catalog/products/{product_id}")
    assert deleted.status_code == 204

    async with db_factory() as session:
        remaining = await session.scalar(select(func.count(ViewCounter.id)))
    assert remaining == 0
