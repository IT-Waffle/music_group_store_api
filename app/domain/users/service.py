from .schemas import UserCreate
from .repository import UserRepository
from app.core.security import get_password_hash


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
