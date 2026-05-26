import logging
from datetime import datetime, timedelta, timezone

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.material import Material
from app.core.config import settings
from app.workers.flashcard_worker import generate_flashcards
from app.workers.material_worker import process_material

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)
logger = logging.getLogger(__name__)


async def requeue_stale_materials(ctx) -> None:  # noqa: ARG001
    """Recover old rows that no longer have a live processing job."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with AsyncSessionLocal() as db:
        pending_result = await db.execute(
            select(Material).where(
                Material.processing_status == "pending",
                Material.created_at < cutoff,
            )
        )
        pending_materials = pending_result.scalars().all()
        processing_result = await db.execute(
            select(Material).where(
                Material.processing_status == "processing",
                Material.created_at < cutoff,
            )
        )
        processing_materials = processing_result.scalars().all()

        for material in processing_materials:
            material.processing_status = "failed"
            material.processing_error = "Processamento interrompido. Tente novamente."
        if processing_materials:
            await db.commit()

    if pending_materials:
        redis = await create_pool(REDIS_SETTINGS)
        try:
            for material in pending_materials:
                await redis.enqueue_job("process_material", str(material.id))
        finally:
            await redis.aclose()

    if pending_materials or processing_materials:
        logger.warning(
            "Recovered stale materials: requeued=%s failed=%s",
            len(pending_materials),
            len(processing_materials),
        )


class WorkerSettings:
    redis_settings = REDIS_SETTINGS
    job_timeout = 300
    max_tries = 3
    on_startup = requeue_stale_materials
    functions = [process_material, generate_flashcards]
