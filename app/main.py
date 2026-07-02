import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.domain.users.router import router as user_router
from app.domain.users.auth_router import router as auth_router
from app.domain.catalog.router import router as catalog_router
from app.domain.localization.router import router as localization_router

os.makedirs("uploads/products", exist_ok=True)

app = FastAPI(title="Music Band & Art Shop API", version="1.0.0")

app.include_router(user_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(localization_router, prefix="/api/v1")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")