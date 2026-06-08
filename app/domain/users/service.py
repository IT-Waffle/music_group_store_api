import uuid

from .schemas import UserCreate, UserUpdate
from .repository import UserRepository
from app.core.security import get_password_hash, verify_password


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def create_user(self, user_data: UserCreate):
        raw_password = user_data.password
        data_dict = user_data.model_dump()

        hashed_password = get_password_hash(raw_password)

        data_dict.pop("password")
        data_dict["hashed_password"] = hashed_password

        return await self.repository.create(data_dict)

    async def authenticate_user(self, email: str, password: str):
        user = await self.repository.get_by_email(email)

        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    async def get_all_users(self, limit: int = 100, offset: int = 0):
        return await self.repository.get_all(limit=limit, offset=offset)

    async def update_user(self, user_id: uuid.UUID, update_data: UserUpdate):
        user = await self.repository.get_by_id(user_id)

        if not user:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)

        if "password" in update_dict:
            raw_password = update_dict.pop("password")
            hashed_password = get_password_hash(raw_password)
            update_dict["hashed_password"] = hashed_password

        return await self.repository.update(user, update_dict)
