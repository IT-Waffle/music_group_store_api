import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.session import get_db
from . import schemas, service, repository, models, dependencies
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    user_data: schemas.UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_admin),
):
    user_service = service.UserService(repository=repository.UserRepository(db))
    try:
        new_user = await user_service.create_user(user_data)
        return new_user
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email is already registered")


@router.get("/me", response_model=schemas.UserResponse)
async def read_users_me(
    current_user: models.User = Depends(dependencies.get_current_user),
):
    return current_user


@router.get("/", response_model=list[schemas.UserResponse])
async def read_users(
    limit: int = 100,
    offset: int = 0,
    current_user: models.User = Depends(dependencies.get_admin),
    db: AsyncSession = Depends(get_db),
):
    user_service = service.UserService(repository=repository.UserRepository(db))

    return await user_service.get_all_users(limit=limit, offset=offset)


@router.patch("/{user_id}", response_model=schemas.UserResponse)
async def update_user(
    user_id: uuid.UUID,
    update_data: schemas.UserUpdate,
    current_user: models.User = Depends(dependencies.get_admin),
    db: AsyncSession = Depends(get_db),
):
    user_service = service.UserService(repository=repository.UserRepository(db))

    updated_user = await user_service.update_user(user_id, update_data)

    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return updated_user
