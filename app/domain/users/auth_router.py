from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import LoginRateLimiter
from app.infrastructure.session import get_db
from app.infrastructure.cache import get_redis
from . import schemas, service, repository
from app.core import security
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    limiter = LoginRateLimiter(redis)
    rate_limit_key = await limiter.ensure_allowed(request, form_data.username)
    user_service = service.UserService(repository=repository.UserRepository(db))

    user = await user_service.authenticate_user(form_data.username, form_data.password)

    if not user:
        await limiter.record_failure(rate_limit_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await limiter.reset(rate_limit_key)
    access_token = security.create_access_token(data={"sub": str(user.id)})

    return schemas.Token(access_token=access_token, token_type="bearer")
