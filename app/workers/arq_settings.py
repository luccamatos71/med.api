import logging
from datetime import datetime, timedelta, timezone

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models.material import Material
from app.core.config import settings
from app.workers.material_worker import process_material

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)
logger = logging.getLogger(__name__)


async def requeue_stale_materials(ctx) -> None:  # noqa: ARG001
    """Recover old rows that no longer have a live processing job."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Material).where(
                or_(
                    Material.processing_status == "pending",
                    Material.processing_status == "processing",
                ),
                Material.created_at < cutoff,
            )
        )
        materials = result.scalars().all()
        if not materials:
            return

        for material in materials:
            material.processing_status = "pending"
            material.processing_error = None
        await db.commit()

    redis = await create_pool(REDIS_SETTINGS)
    try:
        for material in materials:
            await redis.enqueue_job("process_material", str(material.id))
    finally:
        await redis.aclose()

    logger.warning("Requeued %s stale materials", len(materials))


class WorkerSettings:
    redis_settings = REDIS_SETTINGS
    job_timeout = 90
    max_tries = 3
    on_startup = requeue_stale_materials
    functions = [process_material]
