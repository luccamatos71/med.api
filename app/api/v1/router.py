from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.materials import router as materials_router
from app.api.v1.routes.subjects import router as subjects_router
from app.api.v1.routes.topics import router as topics_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(subjects_router)
router.include_router(topics_router)
router.include_router(materials_router)
