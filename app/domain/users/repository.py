import uuid

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession
from .models import User
from typing import Any


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data_dict: dict[str, Any]) -> User:
        new_user = User(**data_dict)
        self.session.add(new_user)

        await self.session.commit()
        await self.session.refresh(new_user)

        return new_user

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()
