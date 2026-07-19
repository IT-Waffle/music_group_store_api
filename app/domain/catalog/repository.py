import uuid
from typing import Any
from sqlalchemy import select, cast, String, delete, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.catalog.models import Product, Category, ProductImage
from app.domain.localization.models import Translation


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_translation(
        self, entity_type: str, entity_id: str, lang: str, key: str, value: str
    ):
        """
        Searches for exitsting translation, if finds - update.
        If not - creates new record
        """
        stmt = select(Translation).where(
            (Translation.entity_id == entity_id)
            & (Translation.entity_type == entity_type)
            & (Translation.key == key)
            & (Translation.lang == lang)
        )
        res = await self.session.execute(stmt)
        translation = res.scalar_one_or_none()

        if translation:
            translation.value = value
        else:
            new_trans = Translation(
                entity_type=entity_type,
                entity_id=entity_id,
                lang=lang,
                key=key,
                value=value,
            )
            self.session.add(new_trans)

    async def commit(self):
        await self.session.commit()

    async def add_product_image(
        self, product_id: uuid.UUID, image_url: str, is_main: bool, sort_order: int
    ) -> ProductImage:
        new_image = ProductImage(
            product_id=product_id,
            image_url=image_url,
            is_main=is_main,
            sort_order=sort_order,
        )
        self.session.add(new_image)
        await self.session.flush()
        return new_image

    async def get_product_model(self, product_id: uuid.UUID) -> Product | None:
        """
        Helper - method to get product ORM model(without translations)
        """
        stmt = select(Product).where(Product.id == product_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_products(
        self, lang: str, only_published: bool = True
    ) -> list[dict[str, Any]]:
        t_title = aliased(Translation)
        t_desc = aliased(Translation)
        product_id_str = cast(Product.id, String)

        stmt = (
            select(
                Product, t_title.value.label("title"), t_desc.value.label("description")
            )
            .select_from(Product)
            .outerjoin(
                t_title,
                (t_title.entity_id == product_id_str)
                & (t_title.entity_type == "product")
                & (t_title.key == "title")
                & (t_title.lang == lang),
            )
            .outerjoin(
                t_desc,
                (t_desc.entity_id == product_id_str)
                & (t_desc.entity_type == "product")
                & (t_desc.key == "description")
                & (t_desc.lang == lang),
            )
        )

        if only_published:
            stmt = stmt.where(Product.is_published.is_(True))

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.Product.id,
                "slug": row.Product.slug,
                "category_id": row.Product.category_id,
                "is_published": row.Product.is_published,
                "in_stock": row.Product.in_stock,
                "created_at": row.Product.created_at,
                "updated_at": row.Product.updated_at,
                "title": row.title or "",
                "description": row.description or "",
                "images": [img for img in row.Product.images if img.is_main],
            }
            for row in rows
        ]

    async def get_product_by_id(
        self, product_id: uuid.UUID, lang: str, only_published: bool = True
    ) -> dict[str, Any] | None:
        t_title = aliased(Translation)
        t_desc = aliased(Translation)

        product_id_str = cast(Product.id, String)

        stmt = (
            select(
                Product, t_title.value.label("title"), t_desc.value.label("description")
            )
            .select_from(Product)
            # connecting table for TITLE
            .outerjoin(
                t_title,
                (t_title.entity_id == product_id_str)
                & (t_title.entity_type == "product")
                & (t_title.key == "title")
                & (t_title.lang == lang),
            )
            # connecting table for DESCRIPTION
            .outerjoin(
                t_desc,
                (t_desc.entity_id == product_id_str)
                & (t_desc.entity_type == "product")
                & (t_desc.key == "description")
                & (t_desc.lang == lang),
            )
        )

        stmt = stmt.where(Product.id == product_id)
        if only_published:
            stmt = stmt.where(Product.is_published.is_(True))

        result = await self.session.execute(stmt)
        row = result.first()

        if not row:
            return None

        product = row.Product

        return {
            "id": product.id,
            "slug": product.slug,
            "category_id": product.category_id,
            "is_published": product.is_published,
            "in_stock": row.Product.in_stock,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
            "title": row.title or "",
            "description": row.description or "",
            "images": product.images,
        }

    async def create_product(
        self, product: Product, translations: list[Translation]
    ) -> uuid.UUID:

        self.session.add(product)

        await self.session.flush()

        product_id_str = str(product.id)

        for t in translations:
            t.entity_id = product_id_str

        self.session.add_all(translations)

        await self.session.commit()

        return product.id

    async def delete_product(self, product_id: uuid.UUID):
        product_id_str = str(product_id)

        stmt_trans = delete(Translation).where(
            (Translation.entity_type == "product")
            & (Translation.entity_id == product_id_str)
        )
        await self.session.execute(stmt_trans)

        stmt_prod = delete(Product).where(Product.id == product_id)
        await self.session.execute(stmt_prod)

        await self.session.commit()

    async def get_all_categories(self, lang: str) -> list[dict[str, Any]]:
        t_title = aliased(Translation)
        category_id_str = cast(Category.id, String)

        stmt = (
            select(Category, t_title.value.label("title"))
            .outerjoin(
                t_title,
                (t_title.entity_id == category_id_str)
                & (t_title.entity_type == "category")
                & (t_title.key == "title")
                & (t_title.lang == lang),
            )
            .order_by(Category.level.asc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.Category.id,
                "parent_id": row.Category.parent_id,
                "slug": row.Category.slug,
                "level": row.Category.level,
                "created_at": row.Category.created_at,
                "updated_at": row.Category.updated_at,
                "title": row.title or "",
            }
            for row in rows
        ]

    async def get_category_by_id(self, category_id: uuid.UUID) -> Category | None:
        stmt = select(Category).where(Category.id == category_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_category(
        self,
        category: Category,
        translations: list[Translation],
    ) -> uuid.UUID:
        self.session.add(category)
        await self.session.flush()

        category_id_str = str(category.id)
        for t in translations:
            t.entity_id = category_id_str

        self.session.add_all(translations)
        await self.session.commit()

        return category.id

    async def get_category_full(
        self, category_id: uuid.UUID, lang: str
    ) -> dict[str, Any] | None:
        t_title = aliased(Translation)
        category_id_str = cast(Category.id, String)

        stmt = (
            select(Category, t_title.value.label("title"))
            .outerjoin(
                t_title,
                (t_title.entity_id == category_id_str)
                & (t_title.entity_type == "category")
                & (t_title.key == "title")
                & (t_title.lang == lang),
            )
            .where(Category.id == category_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()

        if not row:
            return None

        return {
            "id": row.Category.id,
            "parent_id": row.Category.parent_id,
            "slug": row.Category.slug,
            "level": row.Category.level,
            "created_at": row.Category.created_at,
            "updated_at": row.Category.updated_at,
            "title": row.title or "",
        }

    async def has_dependencies(self, category_id: uuid.UUID) -> bool:
        sub_stmt = select(Category.id).where(Category.parent_id == category_id).limit(1)
        sub_res = await self.session.execute(sub_stmt)
        if sub_res.first():
            return True

        prod_stmt = (
            select(Product.id).where(Product.category_id == category_id).limit(1)
        )
        prod_res = await self.session.execute(prod_stmt)

        if prod_res.first():
            return True

        return False

    async def update_category_tree(self, category_id: uuid.UUID, level_delta: int):
        """
        Recursively updates the level of all child categories.
        Uses a Recursive CTE to traverse the tree to any depth.
        """

        if level_delta == 0:
            return

        base = (
            select(Category.id)
            .where(Category.parent_id == category_id)
            .cte(name="descendants", recursive=True)
        )

        alias = aliased(Category)
        rek = select(alias.id).join(base, alias.parent_id == base.c.id)

        descendants_cte = base.union_all(rek)

        stmt = (
            update(Category)
            .where(Category.id.in_(select(descendants_cte.c.id)))
            .values(level=Category.level + level_delta)
        )

        await self.session.execute(stmt)

    async def delete_category(self, category_id: uuid.UUID):
        category_id_str = str(category_id)

        stmt_trans = delete(Translation).where(
            (Translation.entity_type == "category")
            & (Translation.entity_id == category_id_str)
        )

        await self.session.execute(stmt_trans)

        stmt_cat = delete(Category).where(Category.id == category_id)
        await self.session.execute(stmt_cat)

        await self.session.commit()

    async def get_image_by_id(self, image_id: uuid.UUID) -> ProductImage | None:
        stmt = select(ProductImage).where(ProductImage.id == image_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_image(self, image: ProductImage):
        await self.session.delete(image)

    async def unset_other_main_images(
        self, product_id: uuid.UUID, exclude_image_id: uuid.UUID
    ):
        """Gets off is_main flag from all product images, excepting the selected one"""
        stmt = (
            update(ProductImage)
            .where(ProductImage.product_id == product_id)
            .where(ProductImage.id != exclude_image_id)
            .values(is_main=False)
        )
        await self.session.execute(stmt)

    async def ensure_main_image(self, product_id: uuid.UUID):
        """Checks if there is a main image, if noone is main - makes the first as main"""
        stmt = select(ProductImage).where(
            ProductImage.product_id == product_id, ProductImage.is_main.is_(True)
        )
        has_main = (await self.session.execute(stmt)).first()

        if not has_main:
            # Taking the frist image (with lowest sort_order)
            first_img_stmt = (
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order)
                .limit(1)
            )
            first_img = (
                await self.session.execute(first_img_stmt)
            ).scalar_one_or_none()
            if first_img:
                first_img.is_main = True
