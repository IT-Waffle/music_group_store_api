import os
import uuid
import aiofiles
from .schemas import ProductCreate, ProductUpdate, CategoryCreate, CategoryUpdate
from .repository import CatalogRepository
from .models import Product, Category
from app.domain.localization.models import Translation
from app.domain.catalog.models import ProductImage
from fastapi import HTTPException, status, UploadFile


class CatalogService:
    def __init__(self, repository: CatalogRepository):
        self.repository = repository

    UPLOAD_DIR = "uploads/products"

    async def upload_image(
        self,
        product_id: uuid.UUID,
        file: UploadFile,
        is_main: bool,
        sort_order: int,
    ) -> ProductImage:

        product = await self.repository.get_product_model(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        os.makedirs(self.UPLOAD_DIR, exist_ok=True)

        safe_filename = file.filename or "image.jpg"
        ext = safe_filename.split(".")[-1] if "." in safe_filename else "jpg"

        if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
            raise HTTPException(status_code=400, detail="Invalid image format")

        new_filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(self.UPLOAD_DIR, new_filename)

        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        image_url = f"/uploads/products/{new_filename}"

        db_image = await self.repository.add_product_image(
            product_id=product_id,
            image_url=image_url,
            is_main=is_main,
            sort_order=sort_order,
        )

        # Main image logics:
        if is_main:
            # Uploading a main image - getting off is_main flag from others
            await self.repository.unset_other_main_images(
                product_id, exclude_image_id=db_image.id
            )
        else:
            # Uploadinc not a main image - but a lonely one - automaticaly will become a main image
            await self.repository.ensure_main_image(product_id)

        await self.repository.commit()
        return db_image

    async def get_product(self, product_id: uuid.UUID, lang: str):
        return await self.repository.get_product_by_id(product_id, lang)

    async def get_all_products(self, lang: str, only_published: bool = True):
        return await self.repository.get_all_products(lang, only_published)

    async def create_product(self, data: ProductCreate, lang: str):
        product = Product(
            slug=data.slug,
            category_id=data.category_id,
            is_published=data.is_published,
            in_stock=data.in_stock,
        )

        translations = [
            Translation(
                entity_type="product",
                lang="en",
                key="title",
                value=data.title_en,
            ),
            Translation(
                entity_type="product",
                lang="lv",
                key="title",
                value=data.title_lv,
            ),
            Translation(
                entity_type="product",
                lang="ru",
                key="title",
                value=data.title_ru,
            ),
            Translation(
                entity_type="product",
                lang="en",
                key="description",
                value=data.description_en,
            ),
            Translation(
                entity_type="product",
                lang="lv",
                key="description",
                value=data.description_lv,
            ),
            Translation(
                entity_type="product",
                lang="ru",
                key="description",
                value=data.description_ru,
            ),
        ]

        new_product_id = await self.repository.create_product(product, translations)

        return await self.repository.get_product_by_id(new_product_id, lang)

    async def update_product(
        self, product_id: uuid.UUID, data: ProductUpdate, lang: str
    ):

        db_product = await self.repository.get_product_model(product_id)
        if not db_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product Not Found"
            )

        if data.category_id is not None:
            category = await self.repository.get_category_by_id(data.category_id)
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found"
                )
            db_product.category_id = data.category_id

        if data.slug is not None:
            db_product.slug = data.slug

        if data.is_published is not None:
            db_product.is_published = data.is_published

        if data.in_stock is not None:
            db_product.in_stock = data.in_stock

        product_id_str = str(product_id)

        titles = {
            "en": data.title_en,
            "lv": data.title_lv,
            "ru": data.title_ru,
        }
        for lang_code, new_text in titles.items():
            if new_text is not None:
                await self.repository.upsert_translation(
                    "product", product_id_str, lang_code, "title", new_text
                )

        descriptions = {
            "en": data.description_en,
            "lv": data.description_lv,
            "ru": data.description_ru,
        }
        for lang_code, new_text in descriptions.items():
            if new_text is not None:
                await self.repository.upsert_translation(
                    "product", product_id_str, lang_code, "description", new_text
                )

        await self.repository.commit()
        return await self.repository.get_product_by_id(product_id, lang)

    async def delete_product(self, product_id: uuid.UUID):

        db_product = await self.repository.get_product_model(product_id)
        if not db_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product Not Found"
            )

        await self.repository.delete_product(product_id)

    async def get_category(self, category_id: uuid.UUID, lang: str):
        return await self.repository.get_category_full(category_id, lang)

    async def get_all_categories(self, lang: str):
        return await self.repository.get_all_categories(lang)

    async def create_category(self, data: CategoryCreate, lang: str):
        calculated_level = 0

        if data.parent_id:
            parent = await self.repository.get_category_by_id(data.parent_id)
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent category not found",
                )
            calculated_level = parent.level + 1

        category = Category(
            parent_id=data.parent_id,
            slug=data.slug,
            level=calculated_level,
        )

        translations = [
            Translation(
                entity_type="category",
                lang="en",
                key="title",
                value=data.title_en,
            ),
            Translation(
                entity_type="category",
                lang="lv",
                key="title",
                value=data.title_lv,
            ),
            Translation(
                entity_type="category",
                lang="ru",
                key="title",
                value=data.title_ru,
            ),
        ]

        new_category_id = await self.repository.create_category(category, translations)

        return await self.repository.get_category_full(new_category_id, lang)

    async def update_category(
        self, category_id: uuid.UUID, data: CategoryUpdate, lang: str
    ):
        category = await self.repository.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category Not Found",
            )

        if data.slug is not None:
            category.slug = data.slug

        if data.parent_id is not None and data.parent_id != category.parent_id:
            if data.parent_id == category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot be parent to itself",
                )

            new_level = 0
            if data.parent_id != uuid.UUID(int=0):
                parent = await self.repository.get_category_by_id(data.parent_id)
                if not parent:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="New parent category not foud",
                    )
                new_level = parent.level + 1

            level_delta = new_level - category.level

            category.parent_id = data.parent_id
            category.level = new_level

            await self.repository.update_category_tree(category_id, level_delta)

        titles_to_update = {
            "en": data.title_en,
            "lv": data.title_lv,
            "ru": data.title_ru,
        }

        category_id_str = str(category.id)
        for lang_code, new_text in titles_to_update.items():
            if new_text is not None:
                await self.repository.upsert_translation(
                    entity_type="category",
                    entity_id=category_id_str,
                    lang=lang_code,
                    key="title",
                    value=new_text,
                )

        await self.repository.commit()

        return await self.repository.get_category_full(category_id, lang)

    async def delete_category(self, category_id: uuid.UUID):
        category = await self.repository.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        has_deps = await self.repository.has_dependencies(category_id)
        if has_deps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete category: it has subcategories or products attached",
            )
        await self.repository.delete_category(category_id)

    async def delete_product_image(self, image_id: uuid.UUID):
        # 1. looking for a record in db
        image = await self.repository.get_image_by_id(image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        product_id = image.product_id

        # 2. deleting file from disc
        # image_url looks like "/uploads/products/xxx.jpg"
        # cutting first '/' getting a path  "uploads/products/xxx.jpg"
        file_path = image.image_url.lstrip("/")

        if os.path.exists(file_path):
            os.remove(file_path)

        # 3. deleting record from db
        await self.repository.delete_image(image)
        await self.repository.session.flush()

        # setting a new main image if we have deleted old one:
        await self.repository.ensure_main_image(product_id)

        await self.repository.commit()

    async def set_main_image(self, product_id: uuid.UUID, image_id: uuid.UUID) -> ProductImage:
        image = await self.repository.get_image_by_id(image_id)
        if not image or image.product_id != product_id:
            raise HTTPException(status_code=404, detail="Image not found for this product")

        image.is_main = True
        # unseting any other is_main flags
        await self.repository.unset_other_main_images(product_id, exclude_image_id=image.id)
        await self.repository.commit()
        
        return image
