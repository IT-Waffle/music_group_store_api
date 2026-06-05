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
