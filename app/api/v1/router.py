from fastapi import APIRouter

from app.api.v1.routes.assistant import router as assistant_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.exams import router as exams_router
from app.api.v1.routes.study_plans import router as study_plans_router
from app.api.v1.routes.doubts import router as doubts_router
from app.api.v1.routes.doubts import topics_doubts_router
from app.api.v1.routes.flashcards import materials_flashcards_router
from app.api.v1.routes.flashcards import router as flashcards_router
from app.api.v1.routes.materials import router as materials_router
from app.api.v1.routes.reviews import router as reviews_router
from app.api.v1.routes.subjects import router as subjects_router
from app.api.v1.routes.summaries import router as summaries_router
from app.api.v1.routes.summaries import topics_summary_router
from app.api.v1.routes.topics import router as topics_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(assistant_router)
router.include_router(subjects_router)
router.include_router(topics_router)
router.include_router(materials_router)
router.include_router(summaries_router)
router.include_router(topics_summary_router)
router.include_router(materials_flashcards_router)
router.include_router(chat_router)
router.include_router(doubts_router)
router.include_router(topics_doubts_router)
router.include_router(flashcards_router)
router.include_router(reviews_router)
router.include_router(exams_router)
router.include_router(study_plans_router)
