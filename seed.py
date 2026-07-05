import asyncio
from sqlalchemy import select
from app.infrastructure.session import async_session_factory
from app.domain.users.repository import UserRepository
from app.domain.users.service import UserService
from app.domain.users.schemas import UserCreate
from app.domain.users.models import User, UserRole


async def seed_admin():
    # We use async_session_factory directly because get_db() is a generator meant for FastAPI Depends
    async with async_session_factory() as session:
        repo = UserRepository(session)
        svc = UserService(repo)

        # Check if AT LEAST ONE user with ADMIN role exists in the database
        stmt = select(User).where(User.role == UserRole.ADMIN).limit(1)
        result = await session.execute(stmt)
        admin_exists = result.scalar_one_or_none()

        if not admin_exists:
            admin_email = "admin@band.com"
            admin_pass = "admin123"
            print(f"🌱 Creating the first admin: {admin_email} / {admin_pass}")

            admin_data = UserCreate(
                email=admin_email, password=admin_pass, role=UserRole.ADMIN
            )
            await svc.create_user(admin_data)
            print("✅ Admin created successfully!")
        else:
            print(
                "⚡ At least one admin already exists in the system. Skipping creation."
            )


if __name__ == "__main__":
    asyncio.run(seed_admin())
