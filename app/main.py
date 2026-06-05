from fastapi import FastAPI
from app.domain.users.router import router as user_router

app = FastAPI(title="Music Band & Art Shop API", version="1.0.0")

app.include_router(user_router, prefix="/api/v1")