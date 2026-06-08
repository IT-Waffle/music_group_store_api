from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, UserRole
from .repository import UserRepository
from app.infrastructure.session import get_db
from app.core.security import oauth2_scheme, settings
from fastapi import Depends, HTTPException, status
import jwt
import uuid
from jwt.exceptions import InvalidTokenError


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    try:
        parsed_id = uuid.UUID(user_id)
        user = await UserRepository(db).get_by_id(parsed_id)
    except ValueError:
        raise credentials_exception

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def get_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have enough privileges",
        )
    return current_user


async def get_moderator(current_user: User = Depends(get_current_user)) -> User:

    allowed_roles = {UserRole.ADMIN, UserRole.MODERATOR}
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not enough privileges")
    return current_user
