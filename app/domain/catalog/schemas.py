from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field


# ==========================================
# Category Schemas
# ==========================================


class CategoryBase(BaseModel):
    slug: str = Field(..., max_length=255, description="Unique category slug")


class CategoryCreate(CategoryBase):
    parent_id: uuid.UUID | None = Field(
        None, description="Parent category ID, if exists"
    )

    # Category name translations that will come from admin panel at creation time
    title_en: str = Field(..., description="category name in English")
    title_lv: str = Field(..., description="category name in Latvian")
    title_ru: str = Field(..., description="category name in Russian")


class CategoryResponse(CategoryBase):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    level: int
    created_at: datetime
    updated_at: datetime

    # localized category name accoridng to language in request
    title: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryUpdate(BaseModel):
    slug: str | None = Field(None, max_length=255, description="Unique category slug")
    parent_id: uuid.UUID | None = Field(None, description="Parent category ID")

    title_en: str | None = Field(None, description="Category name in English")
    title_lv: str | None = Field(None, description="Category name in Latvian")
    title_ru: str | None = Field(None, description="Category name in Russian")

    model_config = ConfigDict(extra="forbid")


# ==========================================
# Product Schemas
# ==========================================


class ProductBase(BaseModel):
    category_id: uuid.UUID = Field(..., description="Final subcategory ID")
    image_url: str | None = Field(None, max_length=1024, description="link to image")
    is_published: bool = Field(False, description="Product publication flag")
    in_stock: bool = Field(True, description="Is product in stock")


class ProductCreate(ProductBase):
    # Translation table data, will be entered by admin in CMS
    title_en: str = Field(..., description="Product name in English")
    title_lv: str = Field(..., description="Product name in Latvian")
    title_ru: str = Field(..., description="Product name in Russian")

    description_en: str = Field(..., description="Product description in English")
    description_lv: str = Field(..., description="Product description in Latvian")
    description_ru: str = Field(..., description="Product description in Russian")


class ProductResponse(ProductBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # localized product name and description accoridng to language in request
    title: str
    description: str

    model_config = ConfigDict(from_attributes=True)

class ProductUpdate(BaseModel):
    category_id: uuid.UUID | None = Field(None, description="Change category ID")
    image_url: str | None = Field(None, max_length=1024, description="Change image link") 
    is_published: bool | None = Field(None, description="Publish/Unpublish product")
    in_stock: bool | None = Field(None, description="Change stock status")

    title_en: str | None = Field(None, description="Product name in English")
    title_lv: str | None = Field(None, description="Product name in Latvian")
    title_ru: str | None = Field(None, description="Product name in Russian")

    description_en: str | None = Field(None, description="Product description in English")
    description_lv: str | None = Field(None, description="Product description in Latvian")
    description_ru: str | None = Field(None, description="Product description in Russian")

    model_config = ConfigDict(extra="forbid")