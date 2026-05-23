from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.subject import ChildrenCount, SubjectCreate, SubjectResponse, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])


async def _get_subject_or_404(
    subject_id: UUID, user_id: str, db: AsyncSession
) -> Subject:
    result = await db.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return subject


@router.get("", response_model=List[SubjectResponse])
async def list_subjects(
    include_archived: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SubjectResponse]:
    query = select(Subject).where(Subject.user_id == current_user["user_id"])
    if not include_archived:
        query = query.where(Subject.archived == False)
    query = query.order_by(Subject.created_at)

    result = await db.execute(query)
    subjects = result.scalars().all()

    # Attach topic counts
    out = []
    for s in subjects:
        count_res = await db.execute(
            select(func.count()).where(Topic.subject_id == s.id)
        )
        count = count_res.scalar_one()
        resp = SubjectResponse.model_validate(s)
        resp.topic_count = count
        out.append(resp)
    return out


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    body: SubjectCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    # Unique name check (case-insensitive)
    existing = await db.execute(
        select(Subject).where(
            Subject.user_id == current_user["user_id"],
            func.lower(Subject.name) == body.name.strip().lower(),
            Subject.archived == False,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A subject with this name already exists",
        )

    subject = Subject(
        user_id=current_user["user_id"],
        name=body.name.strip(),
        color=body.color,
    )
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return SubjectResponse.model_validate(subject)


@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    subject = await _get_subject_or_404(subject_id, current_user["user_id"], db)
    count_res = await db.execute(select(func.count()).where(Topic.subject_id == subject.id))
    resp = SubjectResponse.model_validate(subject)
    resp.topic_count = count_res.scalar_one()
    return resp


@router.patch("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: UUID,
    body: SubjectUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    subject = await _get_subject_or_404(subject_id, current_user["user_id"], db)

    if body.name is not None:
        # Unique check excluding self
        existing = await db.execute(
            select(Subject).where(
                Subject.user_id == current_user["user_id"],
                func.lower(Subject.name) == body.name.strip().lower(),
                Subject.id != subject_id,
                Subject.archived == False,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Name already in use")
        subject.name = body.name.strip()

    if body.color is not None:
        subject.color = body.color

    await db.commit()
    await db.refresh(subject)
    return SubjectResponse.model_validate(subject)


@router.patch("/{subject_id}/archive", response_model=SubjectResponse)
async def toggle_archive(
    subject_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    subject = await _get_subject_or_404(subject_id, current_user["user_id"], db)
    subject.archived = not subject.archived
    await db.commit()
    await db.refresh(subject)
    return SubjectResponse.model_validate(subject)


@router.get("/{subject_id}/children-count", response_model=ChildrenCount)
async def children_count(
    subject_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChildrenCount:
    await _get_subject_or_404(subject_id, current_user["user_id"], db)
    count_res = await db.execute(select(func.count()).where(Topic.subject_id == subject_id))
    return ChildrenCount(topics=count_res.scalar_one())


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    subject = await _get_subject_or_404(subject_id, current_user["user_id"], db)
    await db.delete(subject)
    await db.commit()
