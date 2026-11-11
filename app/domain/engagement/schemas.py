import re
import unicodedata
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CommentStatus, ContentType

AUTHOR_NAME_MAX = 80
COMMENT_BODY_MAX = 2000

# Zero-width joiner is kept so emoji sequences survive; other invisible
# format characters (bidi overrides, zero-width spaces...) are dropped
# because they can be used to disguise text.
_KEEP_FORMAT_CHARS = {"‍"}


def _drop_invisible(value: str, *, keep_newlines: bool) -> str:
    cleaned = []
    for char in value:
        if char == "\n" and keep_newlines:
            cleaned.append(char)
            continue
        category = unicodedata.category(char)
        if category == "Cc":  # control chars, incl. \t \r \n when not kept
            cleaned.append(" " if char in "\t\n" else "")
        elif category == "Cf" and char not in _KEEP_FORMAT_CHARS:
            continue
        else:
            cleaned.append(char)
    return "".join(cleaned)


def clean_author_name(value: str) -> str:
    value = _drop_invisible(value.replace("\r\n", "\n"), keep_newlines=False)
    return re.sub(r"\s+", " ", value).strip()


def clean_comment_body(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _drop_invisible(value, keep_newlines=True)
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


class ViewCountResponse(BaseModel):
    view_count: int


class CommentCreate(BaseModel):
    # Raw limits are generous; real limits apply after cleaning.
    author_name: str = Field(max_length=AUTHOR_NAME_MAX * 2)
    body: str = Field(max_length=COMMENT_BODY_MAX * 2)
    # Honeypot: hidden field in the form. Humans leave it empty, naive bots
    # fill every input. A filled value is silently discarded.
    website: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("author_name")
    @classmethod
    def validate_author_name(cls, value: str) -> str:
        value = clean_author_name(value)
        if not value:
            raise ValueError("Name must not be empty")
        if len(value) > AUTHOR_NAME_MAX:
            raise ValueError(f"Name must be at most {AUTHOR_NAME_MAX} characters")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        value = clean_comment_body(value)
        if not value:
            raise ValueError("Comment must not be empty")
        if len(value) > COMMENT_BODY_MAX:
            raise ValueError(f"Comment must be at most {COMMENT_BODY_MAX} characters")
        return value


class CommentSubmittedResponse(BaseModel):
    status: Literal["pending"] = "pending"
    message: str = "Your comment has been sent for moderation."


class CommentPublicResponse(BaseModel):
    id: uuid.UUID
    author_name: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    items: list[CommentPublicResponse]
    total: int
    limit: int
    offset: int


class CommentAdminResponse(BaseModel):
    id: uuid.UUID
    target_type: ContentType
    target_id: uuid.UUID
    target_title: str
    author_name: str
    body: str
    status: CommentStatus
    created_at: datetime
    approved_at: datetime | None = None


class AdminCommentListResponse(BaseModel):
    items: list[CommentAdminResponse]
    total: int
    limit: int
    offset: int
