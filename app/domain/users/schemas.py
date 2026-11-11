from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime
import uuid
from .models import UserRole


class UserBase(BaseModel):
    # Column is VARCHAR(50); longer values would fail in the DB with a 500.
    email: EmailStr = Field(max_length=50)
    role: UserRole
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, max_length=50)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)

class UserResponse(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
