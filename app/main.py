import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.request_limits import RequestLimitsMiddleware
from app.domain.catalog.service import CatalogService
from app.domain.users.router import router as user_router
from app.domain.users.auth_router import router as auth_router
from app.domain.catalog.router import router as catalog_router
from app.domain.localization.router import router as localization_router
from app.domain.system.router import router as system_router
from app.domain.music.router import router as music_router
from app.domain.engagement.router import router as engagement_router

os.makedirs("uploads/products", exist_ok=True)
os.makedirs(settings.MUSIC_MEDIA_ROOT / ".tmp", exist_ok=True)

docs_enabled = settings.api_docs_enabled
app = FastAPI(
    title="Music Band & Art Shop API",
    version="1.0.0",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

# Added before CORS so CORS stays the outermost layer and its headers are also
# present on 401/413 answers produced here.
app.add_middleware(
    RequestLimitsMiddleware,
    upload_rules=[
        (
            re.compile(r"^/api/v1/catalog/products/[^/]+/images/?$"),
            lambda: CatalogService.MAX_FILE_SIZE,
        ),
        (
            re.compile(r"^/api/v1/music/manage/tracks/[^/]+/audio/?$"),
            lambda: settings.MUSIC_AUDIO_MAX_BYTES,
        ),
        (
            re.compile(r"^/api/v1/music/manage/tracks/[^/]+/cover/?$"),
            lambda: settings.MUSIC_IMAGE_MAX_BYTES,
        ),
        (
            re.compile(r"^/api/v1/music/manage/clips/[^/]+/poster/?$"),
            lambda: settings.MUSIC_IMAGE_MAX_BYTES,
        ),
        (
            re.compile(r"^/api/v1/music/manage/clips/[^/]+/video/?$"),
            lambda: settings.MUSIC_VIDEO_MAX_BYTES,
        ),
    ],
)

if settings.CORS_ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Accept-Ranges", "Content-Range", "Content-Length"],
    )

app.include_router(user_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(localization_router, prefix="/api/v1")
app.include_router(music_router, prefix="/api/v1")
app.include_router(engagement_router, prefix="/api/v1")


# system routes will be reachable on /health/live and /health/ready
app.include_router(system_router)

app.mount(
    "/uploads/products",
    StaticFiles(directory="uploads/products"),
    name="product_uploads",
)
