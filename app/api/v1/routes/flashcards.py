from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.flashcard import Flashcard
from app.models.flashcard_review import FlashcardReview
from app.models.material import Material
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.flashcard import (
    FlashcardCreate,
    FlashcardGenerateResponse,
    FlashcardResponse,
    FlashcardUpdate,
)
from app.workers.arq_settings import REDIS_SETTINGS

router = APIRouter(prefix="/flashcards", tags=["flashcards"])
materials_flashcards_router = APIRouter(prefix="/materials", tags=["flashcards"])


async def _verify_topic_ownership(topic_id: UUID, user_id: str, db: AsyncSession) -> Topic:
    result = await db.execute(select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


async def _get_flashcard_or_404(flashcard_id: UUID, user_id: str, db: AsyncSession) -> Flashcard:
    result = await db.execute(
        select(Flashcard).where(
            Flashcard.id == flashcard_id,
            Flashcard.user_id == user_id,
            Flashcard.archived_at.is_(None),
        )
    )
    flashcard = result.scalar_one_or_none()
    if not flashcard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")
    return flashcard


async def _verify_material_scope(material_id: UUID, user_id: str, db: AsyncSession) -> Material:
    result = await db.execute(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material


def _row_to_response(row) -> FlashcardResponse:
    flashcard, topic_name, subject_name, material_title, subject_id = row
    response = FlashcardResponse.model_validate(flashcard)
    response.subject_id = subject_id
    response.topic_name = topic_name
    response.subject_name = subject_name
    response.material_title = material_title
    return response


async def _ensure_review_row(db: AsyncSession, flashcard: Flashcard) -> None:
    existing = await db.execute(
        select(FlashcardReview).where(FlashcardReview.flashcard_id == flashcard.id)
    )
    review = existing.scalar_one_or_none()
    if review:
        return
    db.add(
        FlashcardReview(
            flashcard_id=flashcard.id,
            user_id=flashcard.user_id,
            state="new",
            due_date=datetime.now(timezone.utc),
            elapsed_days=0,
            scheduled_days=0,
            reps=0,
            lapses=0,
        )
    )


@materials_flashcards_router.post(
    "/{material_id}/flashcards/generate",
    response_model=FlashcardGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_flashcards_for_material(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardGenerateResponse:
    material = await _verify_material_scope(material_id, current_user["user_id"], db)
    if material.processing_status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Material is not ready",
        )

    redis = await create_pool(REDIS_SETTINGS)
    try:
        await redis.enqueue_job("generate_flashcards", str(material_id))
    finally:
        await redis.aclose()
    return FlashcardGenerateResponse(queued=True)


@router.get("/pending", response_model=list[FlashcardResponse])
async def list_pending_flashcards(
    topic_id: UUID | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FlashcardResponse]:
    user_id = current_user["user_id"]
    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(
            Flashcard.user_id == user_id,
            Flashcard.archived_at.is_(None),
            Flashcard.ai_approved_at.is_(None),
        )
        .order_by(Flashcard.created_at.desc())
    )
    if topic_id:
        stmt = stmt.where(Flashcard.topic_id == topic_id)

    result = await db.execute(stmt)
    return [_row_to_response(row) for row in result.all()]


@router.get("", response_model=list[FlashcardResponse])
async def list_flashcards(
    topic_id: UUID | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FlashcardResponse]:
    user_id = current_user["user_id"]
    filters = [Flashcard.user_id == user_id, Flashcard.archived_at.is_(None)]
    if topic_id:
        filters.append(Flashcard.topic_id == topic_id)
    if subject_id:
        filters.append(Subject.id == subject_id)

    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(and_(*filters))
        .order_by(Flashcard.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_row_to_response(row) for row in result.all()]


@router.get("/{flashcard_id}", response_model=FlashcardResponse)
async def get_flashcard(
    flashcard_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    user_id = current_user["user_id"]
    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(
            Flashcard.id == flashcard_id,
            Flashcard.user_id == user_id,
            Flashcard.archived_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")
    return _row_to_response(row)


@router.post("", response_model=FlashcardResponse, status_code=status.HTTP_201_CREATED)
async def create_flashcard(
    body: FlashcardCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    user_id = current_user["user_id"]
    await _verify_topic_ownership(body.topic_id, user_id, db)
    if body.material_id:
        await _verify_material_scope(body.material_id, user_id, db)

    flashcard = Flashcard(
        user_id=user_id,
        topic_id=body.topic_id,
        material_id=body.material_id,
        source="manual",
        front=body.front.strip(),
        back=body.back.strip(),
        ai_approved_at=datetime.now(timezone.utc),
    )
    db.add(flashcard)
    await db.flush()
    await _ensure_review_row(db, flashcard)
    await db.commit()
    await db.refresh(flashcard)

    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(Flashcard.id == flashcard.id)
    )
    result = await db.execute(stmt)
    return _row_to_response(result.one())


@router.patch("/{flashcard_id}", response_model=FlashcardResponse)
async def update_flashcard(
    flashcard_id: UUID,
    body: FlashcardUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    flashcard = await _get_flashcard_or_404(flashcard_id, current_user["user_id"], db)
    if body.topic_id:
        await _verify_topic_ownership(body.topic_id, current_user["user_id"], db)
        flashcard.topic_id = body.topic_id
    if body.material_id:
        await _verify_material_scope(body.material_id, current_user["user_id"], db)
        flashcard.material_id = body.material_id
    if body.front is not None:
        flashcard.front = body.front.strip()
    if body.back is not None:
        flashcard.back = body.back.strip()
    if body.source_snippet is not None:
        flashcard.source_snippet = body.source_snippet.strip()
    if body.page_number is not None:
        flashcard.page_number = body.page_number
    if body.approve_now or flashcard.source == "manual":
        flashcard.ai_approved_at = flashcard.ai_approved_at or datetime.now(timezone.utc)
        await _ensure_review_row(db, flashcard)

    await db.commit()
    await db.refresh(flashcard)

    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(Flashcard.id == flashcard.id)
    )
    result = await db.execute(stmt)
    return _row_to_response(result.one())


@router.patch("/{flashcard_id}/approve", response_model=FlashcardResponse)
async def approve_flashcard(
    flashcard_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    flashcard = await _get_flashcard_or_404(flashcard_id, current_user["user_id"], db)
    flashcard.ai_approved_at = datetime.now(timezone.utc)
    await _ensure_review_row(db, flashcard)
    await db.commit()
    await db.refresh(flashcard)

    stmt = (
        select(Flashcard, Topic.name, Subject.name, Material.title)
        .add_columns(Subject.id.label("subject_id"))
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .outerjoin(Material, Material.id == Flashcard.material_id)
        .where(Flashcard.id == flashcard.id)
    )
    result = await db.execute(stmt)
    return _row_to_response(result.one())


@router.patch("/{flashcard_id}/discard", response_model=FlashcardResponse)
async def discard_flashcard(
    flashcard_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    flashcard = await _get_flashcard_or_404(flashcard_id, current_user["user_id"], db)
    flashcard.archived_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(flashcard)
    response = FlashcardResponse.model_validate(flashcard)
    return response


@router.delete("/{flashcard_id}", response_model=FlashcardResponse)
async def delete_flashcard(
    flashcard_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    flashcard = await _get_flashcard_or_404(flashcard_id, current_user["user_id"], db)
    flashcard.archived_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(flashcard)
    return FlashcardResponse.model_validate(flashcard)
