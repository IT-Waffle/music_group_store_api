from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.session import get_db
from . import schemas, service, repository
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    user_data: schemas.UserCreate, db: AsyncSession = Depends(get_db)
):
    user_service = service.UserService(repository=repository.UserRepository(db))
    try:
        new_user = await user_service.create_user(user_data)
        return new_user
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email is already registered")
