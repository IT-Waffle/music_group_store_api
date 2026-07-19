import pytest
import io
import uuid


@pytest.mark.asyncio
async def test_get_public_products(async_client):
    """Public route: Anyone can get the list of products"""
    response = await async_client.get("/api/v1/catalog/products")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_category_admin(admin_client):
    """Admin can create categories"""
    payload = {
        "slug": f"test-cat-{uuid.uuid4().hex[:6]}",  # unique slug
        "title_en": "Test Category",
        "title_lv": "Testa Kategorija",
        "title_ru": "Тестовая Категория",
    }
    response = await admin_client.post("/api/v1/catalog/categories", json=payload)
    assert response.status_code == 201
    assert "id" in response.json()


@pytest.mark.asyncio
async def test_upload_image_validation(admin_client):
    """Pillow validation: Blocking fake images (Malware)"""
    # Creating a fake image file (not a real image)
    fake_image = io.BytesIO(b"print('malicious script')")
    files = {"file": ("hacker.jpg", fake_image, "image/jpeg")}

    # Trying to upload to a non-existent product
    fake_product_id = "00000000-0000-0000-0000-000000000000"
    
    response = await admin_client.post(
        f"/api/v1/catalog/products/{fake_product_id}/images",
        files=files,
        data={"is_main": "true", "sort_order": "1"},  # Form data
    )

    # The response should be either 400 (Bad Request) or 404 (Not Found) depending on the validation logic
    # but not the 500 (server error)
    assert response.status_code in [400, 404]


@pytest.mark.asyncio
async def test_unpublished_product_detail_is_not_public(admin_client):
    category = await admin_client.post(
        "/api/v1/catalog/categories",
        json={
            "slug": f"private-category-{uuid.uuid4().hex[:8]}",
            "title_en": "Private",
            "title_lv": "Privāts",
            "title_ru": "Приватный",
        },
    )
    assert category.status_code == 201, category.text
    product = await admin_client.post(
        "/api/v1/catalog/products",
        json={
            "slug": f"private-product-{uuid.uuid4().hex[:8]}",
            "category_id": category.json()["id"],
            "is_published": False,
            "title_en": "Private",
            "title_lv": "Privāts",
            "title_ru": "Приватный",
            "description_en": "Private",
            "description_lv": "Privāts",
            "description_ru": "Приватный",
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    public_detail = await admin_client.get(f"/api/v1/catalog/products/{product_id}")
    assert public_detail.status_code == 404
    admin_detail = await admin_client.get(
        f"/api/v1/catalog/manage/products/{product_id}"
    )
    assert admin_detail.status_code == 200
