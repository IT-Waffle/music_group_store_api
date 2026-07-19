import io
import uuid

import pytest
from PIL import Image

from app.core.config import settings
from app.domain.music.storage import LocalMusicStorage


def translations(prefix: str):
    return {
        "en": {"title": f"{prefix} EN", "description": f"{prefix} description EN"},
        "lv": {"title": f"{prefix} LV", "description": f"{prefix} apraksts LV"},
        "ru": {"title": f"{prefix} RU", "description": f"{prefix} описание RU"},
    }


async def fake_ffprobe(self, path):
    if path.suffix == ".mp3":
        return {
            "format": {"duration": "2.5"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
        }
    if path.suffix == ".m4a":
        return {
            "format": {"duration": "2.5"},
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
        }
    return {
        "format": {"duration": "3.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }


@pytest.mark.asyncio
async def test_full_music_flow(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MUSIC_MEDIA_ROOT", tmp_path / "music")
    monkeypatch.setattr(LocalMusicStorage, "_ffprobe", fake_ffprobe)

    create_response = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={
            "slug": "amor-fati-one",
            "sort_order": 10,
            "release_date": "2026-09-07",
            "translations": translations("Track"),
        },
    )
    assert create_response.status_code == 201, create_response.text
    track_id = create_response.json()["id"]

    public_draft = await admin_client.get("/api/v1/music/tracks")
    assert public_draft.status_code == 200
    assert public_draft.json()["items"] == []

    publish_without_audio = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/publish"
    )
    assert publish_without_audio.status_code == 409
    assert publish_without_audio.json()["detail"]["code"] == "TRACK_AUDIO_REQUIRED"

    audio_response = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"fake-mp3-content", "audio/mpeg")},
    )
    assert audio_response.status_code == 200, audio_response.text
    assert audio_response.json()["duration_ms"] == 2500

    image = io.BytesIO()
    Image.new("RGB", (32, 32), color="black").save(image, format="WEBP")
    cover_response = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/cover",
        files={"file": ("cover.webp", image.getvalue(), "image/webp")},
    )
    assert cover_response.status_code == 200, cover_response.text
    assert cover_response.json()["width"] == 32

    clip_response = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/clips",
        json={
            "sort_order": 1,
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "translations": translations("Clip"),
        },
    )
    assert clip_response.status_code == 201, clip_response.text
    clip_id = clip_response.json()["id"]

    publish_clip_without_video = await admin_client.patch(
        f"/api/v1/music/manage/tracks/{track_id}/clips/{clip_id}",
        json={"is_published": True},
    )
    assert publish_clip_without_video.status_code == 409
    assert publish_clip_without_video.json()["detail"]["code"] == "CLIP_VIDEO_REQUIRED"

    video_response = await admin_client.post(
        f"/api/v1/music/manage/clips/{clip_id}/video",
        files={"file": ("clip.mp4", b"fake-mp4-content", "video/mp4")},
    )
    assert video_response.status_code == 200, video_response.text
    assert video_response.json()["codec"] == "h264/aac"

    publish_clip = await admin_client.patch(
        f"/api/v1/music/manage/tracks/{track_id}/clips/{clip_id}",
        json={"is_published": True},
    )
    assert publish_clip.status_code == 200, publish_clip.text
    assert publish_clip.json()["is_published"] is True

    publish_track = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/publish"
    )
    assert publish_track.status_code == 200, publish_track.text
    assert publish_track.json()["status"] == "published"

    public_tracks = await admin_client.get(
        "/api/v1/music/tracks", headers={"Accept-Language": "ru"}
    )
    assert public_tracks.status_code == 200, public_tracks.text
    assert public_tracks.json()["items"][0]["title"] == "Track RU"
    assert public_tracks.json()["items"][0]["clips"][0]["id"] == clip_id
    assert "original_filename" not in public_tracks.json()["items"][0]["audio"]

    public_clips = await admin_client.get(
        "/api/v1/music/clips", headers={"Accept-Language": "lv"}
    )
    assert public_clips.status_code == 200, public_clips.text
    assert public_clips.json()["items"][0]["title"] == "Clip LV"
    assert public_clips.json()["items"][0]["youtube_url"].startswith("https://")

    clip_detail = await admin_client.get(f"/api/v1/music/clips/{clip_id}")
    assert clip_detail.status_code == 200
    assert clip_detail.json()["video"]["url"].endswith(f"/{clip_id}/video")

    ranged_audio = await admin_client.get(
        "/api/v1/music/tracks/amor-fati-one/audio",
        headers={"Range": "bytes=0-3"},
    )
    assert ranged_audio.status_code == 206
    assert ranged_audio.content == b"fake"
    assert ranged_audio.headers["accept-ranges"] == "bytes"

    head_video = await admin_client.head(f"/api/v1/music/clips/{clip_id}/video")
    assert head_video.status_code == 200
    assert head_video.content == b""

    monkeypatch.setattr(settings, "MEDIA_USE_X_ACCEL_REDIRECT", True)
    accelerated = await admin_client.get("/api/v1/music/tracks/amor-fati-one/audio")
    assert accelerated.status_code == 200
    assert accelerated.headers["x-accel-redirect"].startswith(
        settings.MEDIA_X_ACCEL_PREFIX
    )
    monkeypatch.setattr(settings, "MEDIA_USE_X_ACCEL_REDIRECT", False)

    unpublish = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/unpublish"
    )
    assert unpublish.status_code == 200
    hidden_audio = await admin_client.get("/api/v1/music/tracks/amor-fati-one/audio")
    assert hidden_audio.status_code == 404

    delete_track = await admin_client.delete(f"/api/v1/music/manage/tracks/{track_id}")
    assert delete_track.status_code == 204
    remaining_files = [
        path
        for path in (tmp_path / "music").rglob("*")
        if path.is_file() and ".tmp" not in path.parts
    ]
    assert remaining_files == []


@pytest.mark.asyncio
async def test_clip_external_links_are_optional_and_validated(admin_client):
    track = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={"slug": f"track-{uuid.uuid4().hex}", "translations": translations("T")},
    )
    assert track.status_code == 201
    track_id = track.json()["id"]

    no_links = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/clips",
        json={"translations": translations("C")},
    )
    assert no_links.status_code == 201
    assert no_links.json()["youtube_url"] is None
    assert no_links.json()["vimeo_url"] is None

    invalid_link = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/clips",
        json={
            "youtube_url": "https://example.com/watch?v=bad",
            "translations": translations("Invalid"),
        },
    )
    assert invalid_link.status_code == 422
    assert invalid_link.json()["detail"]["code"] == "INVALID_EXTERNAL_VIDEO_URL"


@pytest.mark.asyncio
async def test_incomplete_translations_block_publication(
    admin_client, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "MUSIC_MEDIA_ROOT", tmp_path / "music")
    monkeypatch.setattr(LocalMusicStorage, "_ffprobe", fake_ffprobe)
    track = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={
            "slug": "incomplete-track",
            "translations": {"en": {"title": "Only English", "description": "Text"}},
        },
    )
    track_id = track.json()["id"]
    await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"fake-mp3-content", "audio/mpeg")},
    )
    response = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/publish"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TRANSLATIONS_REQUIRED"


@pytest.mark.asyncio
async def test_music_upload_rejects_wrong_mime_and_oversize(
    admin_client, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "MUSIC_MEDIA_ROOT", tmp_path / "music")
    track = await admin_client.post(
        "/api/v1/music/manage/tracks",
        json={"slug": "upload-validation", "translations": translations("T")},
    )
    track_id = track.json()["id"]

    wrong_mime = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"content", "application/octet-stream")},
    )
    assert wrong_mime.status_code == 415
    assert wrong_mime.json()["detail"]["code"] == "MEDIA_TYPE_UNSUPPORTED"

    monkeypatch.setattr(settings, "MUSIC_AUDIO_MAX_BYTES", 4)
    too_large = await admin_client.post(
        f"/api/v1/music/manage/tracks/{track_id}/audio",
        files={"file": ("track.mp3", b"12345", "audio/mpeg")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "MEDIA_TOO_LARGE"


@pytest.mark.asyncio
async def test_moderator_cannot_publish(moderator_client):
    track = await moderator_client.post(
        "/api/v1/music/manage/tracks",
        json={"slug": "moderator-track", "translations": translations("T")},
    )
    assert track.status_code == 201
    response = await moderator_client.post(
        f"/api/v1/music/manage/tracks/{track.json()['id']}/publish"
    )
    assert response.status_code == 403


def test_storage_rejects_path_traversal(tmp_path):
    storage = LocalMusicStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.resolve("../../etc/passwd")
