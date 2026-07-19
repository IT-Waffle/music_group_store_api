import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .models import TrackStatus


Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]


class TranslationTextInput(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TranslationsInput(BaseModel):
    en: TranslationTextInput | None = None
    lv: TranslationTextInput | None = None
    ru: TranslationTextInput | None = None

    model_config = ConfigDict(extra="forbid")


class TranslationTextResponse(BaseModel):
    title: str | None = None
    description: str | None = None


class TranslationsResponse(BaseModel):
    en: TranslationTextResponse = Field(default_factory=TranslationTextResponse)
    lv: TranslationTextResponse = Field(default_factory=TranslationTextResponse)
    ru: TranslationTextResponse = Field(default_factory=TranslationTextResponse)


class MusicAssetResponse(BaseModel):
    id: uuid.UUID
    kind: str
    url: str
    content_type: str
    size_bytes: int
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None


class MusicAssetAdminResponse(MusicAssetResponse):
    original_filename: str | None = None


class MusicClipCreate(BaseModel):
    sort_order: int = 0
    youtube_url: str | None = Field(default=None, max_length=2048)
    vimeo_url: str | None = Field(default=None, max_length=2048)
    translations: TranslationsInput = Field(default_factory=TranslationsInput)

    model_config = ConfigDict(extra="forbid")


class MusicClipUpdate(BaseModel):
    sort_order: int | None = None
    is_published: bool | None = None
    youtube_url: str | None = Field(default=None, max_length=2048)
    vimeo_url: str | None = Field(default=None, max_length=2048)
    translations: TranslationsInput | None = None

    model_config = ConfigDict(extra="forbid")


class MusicClipPublicResponse(BaseModel):
    id: uuid.UUID
    track_id: uuid.UUID
    track_slug: str
    title: str
    description: str
    sort_order: int
    video: MusicAssetResponse
    poster: MusicAssetResponse | None = None
    youtube_url: str | None = None
    vimeo_url: str | None = None
    created_at: datetime
    updated_at: datetime


class MusicClipAdminResponse(BaseModel):
    id: uuid.UUID
    track_id: uuid.UUID
    sort_order: int
    is_published: bool
    youtube_url: str | None = None
    vimeo_url: str | None = None
    translations: TranslationsResponse
    video: MusicAssetAdminResponse | None = None
    poster: MusicAssetAdminResponse | None = None
    created_at: datetime
    updated_at: datetime


class MusicTrackCreate(BaseModel):
    slug: Slug
    sort_order: int = 0
    release_date: date | None = None
    translations: TranslationsInput = Field(default_factory=TranslationsInput)

    model_config = ConfigDict(extra="forbid")


class MusicTrackUpdate(BaseModel):
    slug: Slug | None = None
    sort_order: int | None = None
    release_date: date | None = None
    translations: TranslationsInput | None = None

    model_config = ConfigDict(extra="forbid")


class MusicTrackPublicResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    sort_order: int
    release_date: date | None = None
    audio: MusicAssetResponse
    cover: MusicAssetResponse | None = None
    clips: list[MusicClipPublicResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MusicTrackAdminResponse(BaseModel):
    id: uuid.UUID
    slug: str
    status: TrackStatus
    sort_order: int
    release_date: date | None = None
    published_at: datetime | None = None
    translations: TranslationsResponse
    audio: MusicAssetAdminResponse | None = None
    cover: MusicAssetAdminResponse | None = None
    clips: list[MusicClipAdminResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TrackListResponse(BaseModel):
    items: list[MusicTrackPublicResponse]
    total: int
    limit: int
    offset: int


class ClipListResponse(BaseModel):
    items: list[MusicClipPublicResponse]
    total: int
    limit: int
    offset: int


class AdminTrackListResponse(BaseModel):
    items: list[MusicTrackAdminResponse]
    total: int
    limit: int
    offset: int


class MusicErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class MusicErrorResponse(BaseModel):
    detail: MusicErrorDetail
