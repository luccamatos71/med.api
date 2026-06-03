import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.material_summary import MaterialSummary
from app.models.topic import Topic
from app.models.topic_summary import TopicSummary
from app.schemas.summary import SummaryContent, SummaryResponse
from app.services.summary_generator import generate_summary_from_chunks

router = APIRouter(prefix="/materials", tags=["summaries"])
topics_summary_router = APIRouter(prefix="/topics", tags=["summaries"])
logger = logging.getLogger(__name__)


async def _get_owned_material(material_id: UUID, user_id: str, db: AsyncSession) -> Material:
    result = await db.execute(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material


def _to_response(summary: MaterialSummary) -> SummaryResponse:
    return SummaryResponse(
        id=summary.id,
        material_id=summary.material_id,
        summary=SummaryContent.model_validate(summary.summary_json),
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.get("/{material_id}/summary", response_model=SummaryResponse)
async def get_summary(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    user_id = current_user["user_id"]
    await _get_owned_material(material_id, user_id, db)
    result = await db.execute(
        select(MaterialSummary).where(MaterialSummary.material_id == material_id)
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not generated yet")
    return _to_response(summary)


@router.post("/{material_id}/summary", response_model=SummaryResponse)
async def generate_summary(
    material_id: UUID,
    regenerate: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    """Generate (or return cached) the structured summary for a material.

    Synchronous on-demand generation — no background worker (serverless-safe).
    """
    user_id = current_user["user_id"]
    material = await _get_owned_material(material_id, user_id, db)

    existing_result = await db.execute(
        select(MaterialSummary).where(MaterialSummary.material_id == material_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing and not regenerate:
        return _to_response(existing)

    if material.processing_status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Material ainda está sendo processado.",
        )
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    chunks_result = await db.execute(
        select(MaterialChunk.content, MaterialChunk.chunk_metadata)
        .where(MaterialChunk.material_id == material_id, MaterialChunk.user_id == user_id)
        .order_by(MaterialChunk.created_at.asc())
    )
    chunks = [{"content": row.content, "metadata": row.chunk_metadata or {}} for row in chunks_result.all()]
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Material sem conteúdo processado para resumir.",
        )

    try:
        content = await generate_summary_from_chunks(chunks)
    except Exception as exc:
        logger.exception(
            "Summary generation failed",
            extra={"material_id": str(material_id), "user_id": user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao gerar o resumo. Tente novamente.",
        ) from exc

    if existing:
        existing.summary_json = content.model_dump()
        await db.commit()
        await db.refresh(existing)
        return _to_response(existing)

    summary = MaterialSummary(
        material_id=material_id,
        user_id=user_id,
        summary_json=content.model_dump(),
    )
    db.add(summary)
    await db.commit()
    await db.refresh(summary)
    return _to_response(summary)


# ── Topic-level summary (combines all materials of a topic) ──────────────────

def _topic_to_response(summary: TopicSummary) -> SummaryResponse:
    return SummaryResponse(
        id=summary.id,
        material_id=summary.topic_id,  # reuse field as the scope id
        summary=SummaryContent.model_validate(summary.summary_json),
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


async def _topic_chunks(db: AsyncSession, user_id: str, topic_id: UUID) -> list[dict]:
    sub = await db.execute(
        select(Topic.id).where(Topic.parent_topic_id == topic_id, Topic.user_id == user_id)
    )
    topic_ids = [topic_id, *[r[0] for r in sub.all()]]
    mats = await db.execute(
        select(Material.id).where(
            Material.topic_id.in_(topic_ids),
            Material.user_id == user_id,
            Material.processing_status == "ready",
        )
    )
    mat_ids = [r[0] for r in mats.all()]
    if not mat_ids:
        return []
    rows = await db.execute(
        select(MaterialChunk.content, MaterialChunk.chunk_metadata)
        .where(MaterialChunk.material_id.in_(mat_ids), MaterialChunk.user_id == user_id)
        .order_by(MaterialChunk.created_at.asc())
    )
    return [{"content": r.content, "metadata": r.chunk_metadata or {}} for r in rows.all()]


@topics_summary_router.get("/{topic_id}/summary", response_model=SummaryResponse)
async def get_topic_summary(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    user_id = current_user["user_id"]
    res = await db.execute(select(TopicSummary).where(TopicSummary.topic_id == topic_id, TopicSummary.user_id == user_id))
    summary = res.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not generated yet")
    return _topic_to_response(summary)


@topics_summary_router.post("/{topic_id}/summary", response_model=SummaryResponse)
async def generate_topic_summary(
    topic_id: UUID,
    regenerate: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    user_id = current_user["user_id"]
    topic_res = await db.execute(select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id))
    if not topic_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Topic not found")

    existing_res = await db.execute(select(TopicSummary).where(TopicSummary.topic_id == topic_id))
    existing = existing_res.scalar_one_or_none()
    if existing and not regenerate:
        return _topic_to_response(existing)

    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    chunks = await _topic_chunks(db, user_id, topic_id)
    if not chunks:
        raise HTTPException(status_code=409, detail="Tópico sem material processado para resumir.")

    try:
        content = await generate_summary_from_chunks(chunks)
    except Exception as exc:
        logger.exception("Topic summary generation failed", extra={"topic_id": str(topic_id)})
        raise HTTPException(status_code=502, detail="Falha ao gerar o resumo. Tente novamente.") from exc

    if existing:
        existing.summary_json = content.model_dump()
        await db.commit()
        await db.refresh(existing)
        return _topic_to_response(existing)

    summary = TopicSummary(topic_id=topic_id, user_id=user_id, summary_json=content.model_dump())
    db.add(summary)
    await db.commit()
    await db.refresh(summary)
    return _topic_to_response(summary)
