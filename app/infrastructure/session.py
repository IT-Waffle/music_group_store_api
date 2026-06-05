from app.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


engine = create_async_engine(str(settings.POSTGRES_URL))

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, autoflush=False
)


async def get_db():
    async with async_session_factory() as session:
        yield session
