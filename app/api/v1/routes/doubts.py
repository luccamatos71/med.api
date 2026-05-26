from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.doubt import Doubt
from app.models.flashcard import Flashcard
from app.models.material import Material
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.doubt import (
    DoubtCreate,
    DoubtResolveRequest,
    DoubtResponse,
    DoubtSummaryResponse,
    SubjectPendingSummary,
)

router = APIRouter(prefix="/doubts", tags=["doubts"])
topics_doubts_router = APIRouter(prefix="/topics", tags=["doubts"])


async def _verify_topic_ownership(topic_id: UUID, user_id: str, db: AsyncSession) -> Topic:
    result = await db.execute(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


async def _get_doubt_or_404(doubt_id: UUID, user_id: str, db: AsyncSession) -> Doubt:
    result = await db.execute(
        select(Doubt).where(Doubt.id == doubt_id, Doubt.user_id == user_id)
    )
    doubt = result.scalar_one_or_none()
    if not doubt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doubt not found")
    return doubt


async def _verify_material_in_topic_scope(
    material_id: UUID, topic_id: UUID, user_id: str, db: AsyncSession
) -> None:
    subtopics_res = await db.execute(
        select(Topic.id).where(Topic.parent_topic_id == topic_id, Topic.user_id == user_id)
    )
    scope_topic_ids = [topic_id, *subtopics_res.scalars().all()]
    material_res = await db.execute(
        select(Material.id).where(
            Material.id == material_id,
            Material.user_id == user_id,
            Material.topic_id.in_(scope_topic_ids),
        )
    )
    if not material_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found in topic scope",
        )


def _to_response(row) -> DoubtResponse:
    doubt = row[0] if isinstance(row, tuple) else row.Doubt
    topic_name = row[1] if isinstance(row, tuple) else row.topic_name
    subject_name = row[2] if isinstance(row, tuple) else row.subject_name
    response = DoubtResponse.model_validate(doubt)
    response.topic_name = topic_name
    response.subject_name = subject_name
    return response


@router.post("", response_model=DoubtResponse, status_code=status.HTTP_201_CREATED)
async def create_doubt(
    body: DoubtCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DoubtResponse:
    user_id = current_user["user_id"]
    topic = await _verify_topic_ownership(body.topic_id, user_id, db)
    if body.material_id:
        await _verify_material_in_topic_scope(body.material_id, body.topic_id, user_id, db)

    doubt = Doubt(
        user_id=user_id,
        topic_id=body.topic_id,
        material_id=body.material_id,
        question=body.question.strip(),
        ai_answer=body.ai_answer,
        status="pending",
    )
    db.add(doubt)
    await db.commit()
    await db.refresh(doubt)

    subject = await db.execute(select(Subject.name).where(Subject.id == topic.subject_id))
    subject_name = subject.scalar_one_or_none()
    response = DoubtResponse.model_validate(doubt)
    response.topic_name = topic.name
    response.subject_name = subject_name
    return response


@router.get("", response_model=list[DoubtResponse])
async def list_doubts(
    status_filter: str | None = Query(default=None, alias="status"),
    subject_id: UUID | None = None,
    topic_id: UUID | None = None,
    older_than_days: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DoubtResponse]:
    user_id = current_user["user_id"]
    stmt = (
        select(Doubt, Topic.name, Subject.name)
        .join(Topic, Topic.id == Doubt.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .where(Doubt.user_id == user_id)
        .order_by(Doubt.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Doubt.status == status_filter)
    if subject_id:
        stmt = stmt.where(Subject.id == subject_id)
    if topic_id:
        stmt = stmt.where(Doubt.topic_id == topic_id)
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        stmt = stmt.where(Doubt.status == "pending", Doubt.created_at < cutoff)

    result = await db.execute(stmt)
    return [_to_response((d, topic_name, subject_name)) for d, topic_name, subject_name in result.all()]


@router.get("/summary", response_model=DoubtSummaryResponse)
async def get_doubts_summary(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DoubtSummaryResponse:
    user_id = current_user["user_id"]
    total_result = await db.execute(
        select(func.count())
        .select_from(Doubt)
        .where(Doubt.user_id == user_id, Doubt.status == "pending")
    )
    pending_total = int(total_result.scalar_one() or 0)

    grouped_result = await db.execute(
        select(Subject.id, Subject.name, func.count(Doubt.id))
        .select_from(Doubt)
        .join(Topic, Topic.id == Doubt.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .where(Doubt.user_id == user_id, Doubt.status == "pending")
        .group_by(Subject.id, Subject.name)
        .order_by(func.count(Doubt.id).desc())
    )
    pending_by_subject = [
        SubjectPendingSummary(subject_id=subject_id, subject_name=subject_name, pending_count=count)
        for subject_id, subject_name, count in grouped_result.all()
    ]
    return DoubtSummaryResponse(
        pending_total=pending_total,
        pending_by_subject=pending_by_subject,
    )


@topics_doubts_router.get("/{topic_id}/doubts", response_model=list[DoubtResponse])
async def get_topic_doubts(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DoubtResponse]:
    user_id = current_user["user_id"]
    topic = await _verify_topic_ownership(topic_id, user_id, db)
    subject_res = await db.execute(select(Subject.name).where(Subject.id == topic.subject_id))
    subject_name = subject_res.scalar_one_or_none()

    result = await db.execute(
        select(Doubt)
        .where(Doubt.topic_id == topic_id, Doubt.user_id == user_id)
        .order_by(Doubt.created_at.desc())
    )
    doubts = []
    for doubt in result.scalars().all():
        response = DoubtResponse.model_validate(doubt)
        response.topic_name = topic.name
        response.subject_name = subject_name
        doubts.append(response)
    return doubts


@router.patch("/{doubt_id}/resolve", response_model=DoubtResponse)
async def resolve_doubt(
    doubt_id: UUID,
    body: DoubtResolveRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DoubtResponse:
    user_id = current_user["user_id"]
    doubt = await _get_doubt_or_404(doubt_id, user_id, db)
    topic = await _verify_topic_ownership(doubt.topic_id, user_id, db)

    if body.create_flashcard:
        flashcard = Flashcard(
            user_id=user_id,
            topic_id=doubt.topic_id,
            material_id=doubt.material_id,
            doubt_id=doubt.id,
            source="from_doubt",
            front=doubt.question,
            back=doubt.ai_answer or "",
            source_snippet=doubt.question[:240],
            ai_approved_at=None,
        )
        db.add(flashcard)
        await db.flush()
        doubt.status = "converted_to_flashcard"
        doubt.flashcard_id = flashcard.id
    else:
        doubt.status = "resolved"

    doubt.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(doubt)

    subject_res = await db.execute(select(Subject.name).where(Subject.id == topic.subject_id))
    subject_name = subject_res.scalar_one_or_none()
    response = DoubtResponse.model_validate(doubt)
    response.topic_name = topic.name
    response.subject_name = subject_name
    return response
