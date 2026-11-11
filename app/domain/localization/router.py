import uuid
from typing import List, Dict
from fastapi import APIRouter, Depends, status, Query, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import json
from redis.asyncio import Redis


from app.infrastructure.session import get_db
from app.infrastructure.cache import get_redis
from app.domain.users.dependencies import get_moderator, get_admin
from . import schemas, service, repository

router = APIRouter(prefix="/localization", tags=["Localization"])

# Texts of publishable content (titles/descriptions of products, tracks and
# clips) are delivered localized by their own endpoints, which respect
# publication. The public localization endpoints must not expose them,
# otherwise drafts and archived items could be read here.
PRIVATE_ENTITY_TYPES = {"product", "music_track", "music_clip"}


def ensure_public_entity_type(entity_type: str) -> None:
    if entity_type in PRIVATE_ENTITY_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# --- (Dependency Injection) ---
def get_localization_service(
    session: AsyncSession = Depends(get_db),
) -> service.LocalizationService:
    repo = repository.LocalizationRepository(session)
    return service.LocalizationService(repo)


async def invalidate_localization_cache(redis: Redis):
    """Deletes all keys starting with 'loc:'"""
    async for key in redis.scan_iter("loc:*"):
        await redis.delete(key)


# ==========================================
# 1. Optimized endpoints for frontend (with automatic grouping and flattening)
# ==========================================


@router.get("/flat/{entity_type}/{entity_id}", response_model=Dict[str, str])
async def get_flat_translations(
    entity_type: str,
    entity_id: str,
    accept_language: str = Header(default="en"),
    svc: service.LocalizationService = Depends(get_localization_service),
    redis: Redis = Depends(get_redis),
):
    """
    A universal compactor. Returns a flat dictionary of {key: value} for ANY entity.
    Example: GET /localization/flat/ui/header -> {"login": "Login", "logout": "Logout"}
    Example: GET /localization/flat/category/uuid-1 -> {"title": "Vinyl Records"}
    """
    ensure_public_entity_type(entity_type)
    lang = accept_language[:2].lower()
    cache_key = f"loc:flat:{lang}:{entity_type}:{entity_id}"

    # trying to load for, cache
    cached_data = await redis.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    # if not found in chache - geting data from db
    translations = await svc.get_all_translations(
        lang=lang, entity_type=entity_type, entity_id=entity_id
    )
    result = {t.key: t.value for t in translations}

    # Cache for 24h, but only real data: caching empty answers would let
    # anyone fill Redis with keys for made-up ids.
    if result:
        await redis.set(cache_key, json.dumps(result), ex=86400)
    return result


@router.get("/bundle/{entity_type}", response_model=Dict[str, Dict[str, str]])
async def get_translations_bundle(
    entity_type: str,
    accept_language: str = Header(default="en"),
    svc: service.LocalizationService = Depends(get_localization_service),
    redis: Redis = Depends(get_redis),
):
    """
    A vacuum cleaner for the frontend. Groups ALL translations of the specified type by their entity_id.
    Example: GET /localization/bundle/category ->
    {
       "uuid-category-1": { "title": "Merch" },
       "uuid-category-2": { "title": "Vinyls" }
    }
    Example: GET /localization/bundle/ui ->
    {
       "header": { "login": "Login" },
       "footer": { "copyright": "All rights reserved" }
    }
    """
    ensure_public_entity_type(entity_type)
    lang = accept_language[:2].lower()
    cache_key = f"loc:bundle:{lang}:{entity_type}"

    # looking for data in cache
    cached_data = await redis.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    # if not foung in cache - getting data from db
    translations = await svc.get_all_translations(lang=lang, entity_type=entity_type)
    bundle = {}
    for t in translations:
        if t.entity_id not in bundle:
            bundle[t.entity_id] = {}
        bundle[t.entity_id][t.key] = t.value

    # saving to the cache (non-empty only, see flat endpoint)
    if bundle:
        await redis.set(cache_key, json.dumps(bundle), ex=86400)
    return bundle


# ==========================================
# 2. Standard CRUD for Admin Panel (CMS)
# ==========================================


@router.get("/translations", response_model=List[schemas.TranslationResponse])
async def get_all_translations(
    lang: str | None = Query(None, description="Filter by language (ru, en, lv)"),
    entity_type: str | None = Query(
        None, description="Filter by type (product, category, ui)"
    ),
    entity_id: str | None = Query(
        None, description="Filter by ID of the specific entity"
    ),
    svc: service.LocalizationService = Depends(get_localization_service),
    current_user=Depends(get_moderator),
):
    """Raw list for the admin panel. Needed for building tables and finding duplicates."""
    return await svc.get_all_translations(lang, entity_type, entity_id)


@router.get(
    "/translations/{translation_id}", response_model=schemas.TranslationResponse
)
async def get_translation(
    translation_id: uuid.UUID,
    svc: service.LocalizationService = Depends(get_localization_service),
    current_user=Depends(get_moderator),
):
    translation = await svc.get_translation(translation_id)
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    return translation


@router.post(
    "/translations",
    response_model=schemas.TranslationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_translation(
    translation_in: schemas.TranslationCreate,
    svc: service.LocalizationService = Depends(get_localization_service),
    current_user=Depends(get_moderator),
    redis: Redis = Depends(get_redis),
):
    result = await svc.create_translation(translation_in)
    await invalidate_localization_cache(redis)  #
    return result


@router.patch(
    "/translations/{translation_id}",
    response_model=schemas.TranslationResponse,
)
async def update_translation(
    translation_id: uuid.UUID,
    translation_in: schemas.TranslationUpdate,
    svc: service.LocalizationService = Depends(get_localization_service),
    current_user=Depends(get_moderator),
    redis: Redis = Depends(get_redis),
):
    result = await svc.update_translation(translation_id, translation_in)
    await invalidate_localization_cache(redis)
    return result


@router.delete("/translations/{translation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_translation(
    translation_id: uuid.UUID,
    svc: service.LocalizationService = Depends(get_localization_service),
    current_user=Depends(get_admin),
    redis: Redis = Depends(get_redis),
):
    await svc.delete_translation(translation_id)
    await invalidate_localization_cache(redis)
