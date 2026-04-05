from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import close_database_connection, get_db_session, test_database_connection

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await test_database_connection()
    yield
    await close_database_connection()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


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
