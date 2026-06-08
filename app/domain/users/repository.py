import uuid
from typing import Sequence
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
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[User]:
        result = await self.session.execute(select(User).limit(limit).offset(offset))
        return result.scalars().all()
    
    async def update(self, user: User, update_data: dict[str, Any]) -> User:
        for key, value in update_data.items():
            setattr(user, key, value)

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user