import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_db
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routes.admin import requests as admin_requests
from app.routes.public import chat as public_chat
from app.routes import ui
from app.routes.public import requests as public_requests

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()

app = FastAPI(
    title = "Temporary Web Chat",
    version = "0.1.0",
    lifespan=lifespan,
)

logger = logging.getLogger(__name__)

app.include_router(public_requests.router)
app.include_router(public_chat.router)
app.include_router(admin_requests.router)
app.include_router(ui.router)


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