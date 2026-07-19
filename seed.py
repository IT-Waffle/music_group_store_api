import asyncio
import os
import sys
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
            admin_email = os.getenv("FIRST_ADMIN_EMAIL")
            admin_pass = os.getenv("FIRST_ADMIN_PASSWORD")
            if not admin_email or not admin_pass:
                print(
                    "FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD are required",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            if len(admin_pass) < 12 or admin_pass.startswith("replace-with-"):
                print(
                    "FIRST_ADMIN_PASSWORD must be a non-placeholder value with at least 12 characters",
                    file=sys.stderr,
                )
                raise SystemExit(2)

            print(f"Creating the first admin: {admin_email}")

            admin_data = UserCreate(
                email=admin_email, password=admin_pass, role=UserRole.ADMIN
            )
            await svc.create_user(admin_data)
            print("Admin created successfully")
        else:
            print("At least one admin already exists; skipping creation")


if __name__ == "__main__":
    asyncio.run(seed_admin())
