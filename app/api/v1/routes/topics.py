from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.topic import ReorderRequest, TopicCreate, TopicResponse, TopicUpdate

router = APIRouter(prefix="/topics", tags=["topics"])


async def _get_topic_or_404(topic_id: UUID, user_id: str, db: AsyncSession) -> Topic:
    result = await db.execute(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


def _build_tree(topics: list[Topic]) -> list[TopicResponse]:
    """Build nested topic tree from flat list."""
    by_id = {t.id: TopicResponse.model_validate(t) for t in topics}
    roots: list[TopicResponse] = []
    for t in topics:
        resp = by_id[t.id]
        if t.parent_topic_id is None:
            roots.append(resp)
        else:
            parent = by_id.get(t.parent_topic_id)
            if parent:
                parent.subtopics.append(resp)
    # Sort by position
    roots.sort(key=lambda x: x.position)
    for r in roots:
        r.subtopics.sort(key=lambda x: x.position)
    return roots


@router.get("", response_model=List[TopicResponse])
async def list_topics(
    subject_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TopicResponse]:
    # Verify subject ownership
    res = await db.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == current_user["user_id"])
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    result = await db.execute(
        select(Topic)
        .where(Topic.subject_id == subject_id, Topic.user_id == current_user["user_id"])
        .order_by(Topic.position)
    )
    topics = list(result.scalars().all())
    return _build_tree(topics)


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    body: TopicCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TopicResponse:
    # Verify subject
    res = await db.execute(
        select(Subject).where(Subject.id == body.subject_id, Subject.user_id == current_user["user_id"])
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    # Hierarchy enforcement: max 2 levels
    if body.parent_topic_id:
        parent_res = await db.execute(
            select(Topic).where(Topic.id == body.parent_topic_id, Topic.user_id == current_user["user_id"])
        )
        parent = parent_res.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent topic not found")
        if parent.parent_topic_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Hierarquia máxima é de 2 níveis (Tópico > Subtópico)",
            )

    # Get next position
    from sqlalchemy import func
    pos_res = await db.execute(
        select(func.count()).where(
            Topic.subject_id == body.subject_id,
            Topic.parent_topic_id == body.parent_topic_id,
        )
    )
    position = pos_res.scalar_one()

    topic = Topic(
        subject_id=body.subject_id,
        user_id=current_user["user_id"],
        parent_topic_id=body.parent_topic_id,
        name=body.name.strip(),
        position=position,
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TopicResponse:
    topic = await _get_topic_or_404(topic_id, current_user["user_id"], db)
    # Load subtopics
    subs_res = await db.execute(
        select(Topic).where(Topic.parent_topic_id == topic_id).order_by(Topic.position)
    )
    resp = TopicResponse.model_validate(topic)
    resp.subtopics = [TopicResponse.model_validate(s) for s in subs_res.scalars().all()]
    return resp


@router.patch("/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: UUID,
    body: TopicUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TopicResponse:
    topic = await _get_topic_or_404(topic_id, current_user["user_id"], db)
    topic.name = body.name.strip()
    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    topic = await _get_topic_or_404(topic_id, current_user["user_id"], db)
    await db.delete(topic)
    await db.commit()


@router.patch("/reorder", response_model=List[TopicResponse])
async def reorder_topics(
    body: ReorderRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TopicResponse]:
    updated = []
    for item in body.items:
        result = await db.execute(
            select(Topic).where(Topic.id == item.id, Topic.user_id == current_user["user_id"])
        )
        topic = result.scalar_one_or_none()
        if topic:
            topic.position = item.position
            updated.append(TopicResponse.model_validate(topic))
    await db.commit()
    return updated
