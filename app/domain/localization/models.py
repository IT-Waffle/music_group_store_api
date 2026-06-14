from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.base import Base


class Translation(Base):
    __tablename__ = "translations"

    entity_type: Mapped[str] = mapped_column(String(50),index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255),index=True, nullable=False)
    lang: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(255),index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
