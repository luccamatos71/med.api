from contextlib import asynccontextmanager
import logging

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.api.v1.router import router as v1_router
from app.embedded_worker import start_embedded_worker, stop_embedded_worker

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_embedded_worker()
    try:
        yield
    finally:
        await stop_embedded_worker()


app = FastAPI(title=".med API", version="0.1.0", lifespan=lifespan)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_request: Request, exc: SQLAlchemyError):
    logger.exception("Database error while handling request", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )


@app.exception_handler(PermissionError)
async def permission_exception_handler(_request: Request, exc: PermissionError):
    logger.exception("Permission/network error while handling request", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Infrastructure temporarily unavailable"},
    )
