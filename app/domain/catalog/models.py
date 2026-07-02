from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.base import Base
import uuid


class Category(Base):
    __tablename__ = "categories"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"

    slug: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    
    is_published: Mapped[bool] = mapped_column(default=False)
    in_stock: Mapped[bool] = mapped_column(default=True)

    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        cascade="all, delete-orphan",
        lazy="selectin", 
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    is_main: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(default=0)
