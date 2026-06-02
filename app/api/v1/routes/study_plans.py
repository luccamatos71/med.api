import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.study_plan import StudyPlan
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.study_plan import StudyPlanCreate, StudyPlanResponse
from app.services.study_plan_generator import build_plan, generate_overview

router = APIRouter(prefix="/study-plans", tags=["study-plans"])
logger = logging.getLogger(__name__)


def _to_response(plan: StudyPlan) -> StudyPlanResponse:
    data = plan.plan_json
    return StudyPlanResponse(
        id=plan.id,
        exam_date=plan.exam_date,
        status=plan.status,
        overview=data.get("overview", ""),
        summary=data.get("summary", {}),
        days=data.get("days", []),
        created_at=plan.created_at,
    )


@router.post("", response_model=StudyPlanResponse)
async def create_study_plan(
    body: StudyPlanCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudyPlanResponse:
    user_id = current_user["user_id"]
    if body.exam_date <= date.today():
        raise HTTPException(status_code=422, detail="A data da prova deve ser no futuro.")

    # Resolve subjects (default: all of the user's) and their topics.
    subj_query = select(Subject).where(Subject.user_id == user_id)
    if body.subject_ids:
        subj_query = subj_query.where(Subject.id.in_(body.subject_ids))
    subjects = (await db.execute(subj_query)).scalars().all()
    if not subjects:
        raise HTTPException(status_code=409, detail="Nenhuma matéria encontrada para montar o plano.")

    subject_names = [s.name for s in subjects]
    subject_ids = [s.id for s in subjects]
    name_by_id = {s.id: s.name for s in subjects}

    topics_rows = (
        await db.execute(
            select(Topic).where(Topic.subject_id.in_(subject_ids), Topic.user_id == user_id)
        )
    ).scalars().all()
    topics = [
        {"id": t.id, "name": t.name, "subject_id": t.subject_id, "subject_name": name_by_id.get(t.subject_id)}
        for t in topics_rows
    ]
    if not topics:
        raise HTTPException(status_code=409, detail="Suas matérias ainda não têm tópicos.")

    plan = build_plan(today=date.today(), exam_date=body.exam_date, topics=topics)
    overview = await generate_overview(
        exam_date=body.exam_date,
        total_days=plan["summary"]["total_days"],
        subjects=subject_names,
        topic_count=len(topics),
    )
    plan_json = {"overview": overview, **plan}

    # Archive previous active plans.
    await db.execute(
        update(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.status == "active")
        .values(status="archived")
    )
    new_plan = StudyPlan(user_id=user_id, exam_date=body.exam_date, status="active", plan_json=plan_json)
    db.add(new_plan)
    await db.commit()
    await db.refresh(new_plan)
    return _to_response(new_plan)


@router.get("/active", response_model=StudyPlanResponse | None)
async def get_active_plan(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudyPlanResponse | None:
    user_id = current_user["user_id"]
    res = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.status == "active")
        .order_by(StudyPlan.created_at.desc())
        .limit(1)
    )
    plan = res.scalar_one_or_none()
    return _to_response(plan) if plan else None


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = current_user["user_id"]
    res = await db.execute(
        select(StudyPlan).where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
    )
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    plan.status = "archived"
    await db.commit()
