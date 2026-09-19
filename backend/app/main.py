import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_db

@asynccontextmanager
async def lifespan(app: FastAPI):

    yield

    await engine.dispose()

app = FastAPI(
    title = "Temporary Web Chat",
    version = "0.1.0",
    lifespan=lifespan,
)

logger = logging.getLogger(__name__)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unreachable"},
        )
    return {"status": "ok", "database": "ok"}