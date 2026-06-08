import enum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.base import Base

# --- Enumerations for strict typing ---


class UserRole(str, enum.Enum):
    """User roles for access control"""

    ADMIN = "admin"  # the internal god
    MODERATOR = "moderator"  # can manage content but not users


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True)
