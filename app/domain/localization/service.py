import uuid
from fastapi import HTTPException, status

from .schemas import TranslationCreate, TranslationUpdate
from .repository import LocalizationRepository
from .models import Translation


class LocalizationService:
    def __init__(self, repository: LocalizationRepository):
        self.repository = repository

    protected_entities = ["product", "category"]

    async def get_translation(self, translation_id: uuid.UUID) -> Translation | None:
        return await self.repository.get_translation_by_id(translation_id)

    async def get_all_translations(
        self,
        lang: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[Translation]:

        return await self.repository.get_all_translations(lang, entity_type, entity_id)

    async def create_translation(
        self, translation_in: TranslationCreate
    ) -> Translation:

        existing = await self.repository.get_by_composite_key(
            entity_type=translation_in.entity_type,
            entity_id=translation_in.entity_id,
            lang=translation_in.lang,
            key=translation_in.key,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Translation for [{translation_in.lang}] '{translation_in.key}' already exists in {translation_in.entity_type}:{translation_in.entity_id}",
            )
        if translation_in.entity_type in self.protected_entities :
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Translations for products and categories must be created via the Catalog API.",
            )

        translation = Translation(
            entity_type=translation_in.entity_type,
            entity_id=translation_in.entity_id,
            lang=translation_in.lang,
            key=translation_in.key,
            value=translation_in.value,
        )
        created_translation = await self.repository.create_translation(translation)
        await self.repository.commit()
        return created_translation

    async def update_translation(
        self,
        translation_id: uuid.UUID,
        translation_in: TranslationUpdate,
    ) -> Translation | None:
        updated_translation = await self.repository.update_translation(
            translation_id, translation_in.value
        )
        if updated_translation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Translation with id {translation_id} not found",
            )
        await self.repository.commit()
        return updated_translation

    async def delete_translation(self, translation_id: uuid.UUID):

        existing = await self.repository.get_translation_by_id(translation_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Translation with id {translation_id} not found",
            )

        # Security: Dissallow deletion of translations for certain entity types that are managed by the Catalog
        # This prevents accidental or unauthorized removal of critical translations.
        # List of entity types that are managed by the Catalog and should not be deleted via the Localization
        
        if existing.entity_type in self.protected_entities:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot delete translation for '{existing.entity_type}'. It is managed by the Catalog API.",
            )

        # If the translation is not protected, proceed with deletion
        await self.repository.delete_translation(translation_id)
        await self.repository.commit()
