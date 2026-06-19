import uuid
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.localization.models import Translation


class LocalizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self):
        """
        After all finished service should call this method to commit all changes to the database.
        This allows to do multiple operations in one transaction.
        """
        await self.session.commit()

    async def get_by_composite_key(
        self,
        entity_type: str,
        entity_id: str,
        lang: str,
        key: str,
    ) -> Translation | None:
        """
        Looks for translation by composite key (entity_type, entity_id, lang, key)
        """
        stmt = select(Translation).where(
            (Translation.entity_type == entity_type)
            & (Translation.entity_id == entity_id)
            & (Translation.lang == lang)
            & (Translation.key == key)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_translation_by_id(self, id: uuid.UUID) -> Translation | None:
        stmt = select(Translation).where(Translation.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_translations(
        self,
        lang: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[Translation]:
        """
        Returns all translations matching the optional filters. If no filters are provided, returns all translations.
        Returns ORM models, pydantic will make JSON from them automatically.
        """
        stmt = select(Translation)

        if lang:
            stmt = stmt.where(Translation.lang == lang)
        if entity_type:
            stmt = stmt.where(Translation.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(Translation.entity_id == entity_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_translation(self, translation: Translation) -> Translation:
        self.session.add(translation)
        await self.session.flush()

        return translation

    async def update_translation(
        self, id: uuid.UUID, new_value: str
    ) -> Translation | None:

        stmt = (
            update(Translation)
            .where(Translation.id == id)
            .values(value=new_value)
            .returning(Translation)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_translation(self, id: uuid.UUID):
        stmt = delete(Translation).where(Translation.id == id)
        await self.session.execute(stmt)
