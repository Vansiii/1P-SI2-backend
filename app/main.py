from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import (
    close_database_connection,
    create_database_tables,
    get_db_session,
    test_database_connection,
)
from .routers.auth import router as auth_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await test_database_connection()
    await create_database_tables()
    yield
    await close_database_connection()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "API de FastAPI inicializada correctamente"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/db/health")
async def database_health_check(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"database": "connected"}
