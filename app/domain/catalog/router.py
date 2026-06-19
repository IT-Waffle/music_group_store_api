import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List

from app.infrastructure.session import get_db
from . import schemas, service, repository
from app.domain.users.dependencies import get_moderator, get_admin

router = APIRouter(prefix="/catalog", tags=["Catalog"])


def get_catalog_service(
    session: AsyncSession = Depends(get_db),
) -> service.CatalogService:
    repo = repository.CatalogRepository(session)
    return service.CatalogService(repo)


@router.get("/products", response_model=List[schemas.ProductResponse])
async def get_products(
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
):
    lang = accept_language[:2].lower()

    return await svc.get_all_products(lang, only_published=True)


# router for admin panel to see all products
@router.get("/manage/products", response_model=List[schemas.ProductResponse])
async def get_all_products_for_admin(
    only_published: bool = Query(
        default=False, description="If true - gives only published"
    ),
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_moderator),
):
    lang = accept_language[:2].lower()

    return await svc.get_all_products(lang, only_published=only_published)


@router.patch("/products/{product_id}", response_model=schemas.ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    product_in: schemas.ProductUpdate,
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_moderator),
):
    lang = accept_language[:2].lower()
    try:
        return await svc.update_product(product_id, product_in, lang)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Integrity Error"
        )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_moderator),
):
    await svc.delete_product(product_id)


@router.get(
    "/products/{product_id}",
    response_model=schemas.ProductResponse,
)
async def get_product(
    product_id: uuid.UUID,
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
):
    lang = accept_language[:2].lower()
    product = await svc.get_product(product_id, lang)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product Not Found"
        )

    return product


@router.post(
    "/products",
    response_model=schemas.ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    product_in: schemas.ProductCreate,
    accept_langueage: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_moderator),
):
    lang = accept_langueage[:2].lower()

    try:
        return await svc.create_product(product_in, lang)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Category ID does not exist"
        )


@router.get(
    "/categories",
    response_model=List[schemas.CategoryResponse],
)
async def get_categories(
    accepted_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
):
    lang = accepted_language[:2].lower()
    return await svc.get_all_categories(lang)


@router.get(
    "/categories/{category_id}",
    response_model=schemas.CategoryResponse,
)
async def get_category(
    category_id: uuid.UUID,
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
):
    lang = accept_language[:2].lower()
    category = await svc.get_category(category_id, lang)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category Not Found"
        )

    return category


@router.post(
    "/categories",
    response_model=schemas.CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    category_in: schemas.CategoryCreate,
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_moderator),
):
    lang = accept_language[:2].lower()

    try:
        return await svc.create_category(category_in, lang)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this slug already exists",
        )


@router.patch(
    "/categories/{category_id}",
    response_model=schemas.CategoryResponse,
)
async def update_category(
    category_id: uuid.UUID,
    category_in: schemas.CategoryUpdate,
    accept_language: str = Header(default="en"),
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_admin),
):
    lang = accept_language[:2].lower()
    try:
        return await svc.update_category(category_id, category_in, lang)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this slug already exists or parent is invalid",
        )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_category(
    category_id: uuid.UUID,
    svc: service.CatalogService = Depends(get_catalog_service),
    current_user=Depends(get_admin),
):
    await svc.delete_category(category_id)
