from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field


class TranslationBase(BaseModel):
    entity_type: str = Field(
        ...,
        max_length=50,
        description="Entity type (e.g., 'product', 'category', 'ui')",
    )
    entity_id: str = Field(
        ...,
        max_length=255,
        description="Entity ID as string",
    )


class TranslationCreate(TranslationBase):
    lang: str = Field(
        ...,
        max_length=10,
        description="Language code (e.g., 'en', 'lv', 'ru')",
    )
    key: str = Field(
        ...,
        max_length=255,
        description="Translation key",
    )
    value: str = Field(
        ...,
        description="Translation value",
    )


class TranslationResponse(TranslationBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    lang: str
    key: str
    value: str

    model_config = ConfigDict(from_attributes=True)


class TranslationUpdate(BaseModel):
    # Only value can be updated, other fields are identifiers and should not be changed
    value: str = Field(
        ...,
        description="New translation value",
    )

    model_config = ConfigDict(extra="forbid")
