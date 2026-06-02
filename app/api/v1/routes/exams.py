import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.exam import ExamSession
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.exam import (
    ExamAnswers,
    ExamCreate,
    ExamQuestionPublic,
    ExamQuestionResult,
    ExamResult,
    ExamSessionPublic,
)
from app.services.exam_generator import generate_exam_from_chunks

router = APIRouter(prefix="/exams", tags=["exams"])
logger = logging.getLogger(__name__)


async def _scope(db: AsyncSession, user_id: str, scope_type: str, scope_id: UUID) -> tuple[list[UUID], str | None]:
    """Return (topic_ids, scope_name) for the exam scope, validating ownership."""
    if scope_type == "topic":
        res = await db.execute(select(Topic).where(Topic.id == scope_id, Topic.user_id == user_id))
        topic = res.scalar_one_or_none()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        sub = await db.execute(
            select(Topic.id).where(Topic.parent_topic_id == scope_id, Topic.user_id == user_id)
        )
        return [scope_id, *[r[0] for r in sub.all()]], topic.name
    # subject
    res = await db.execute(select(Subject).where(Subject.id == scope_id, Subject.user_id == user_id))
    subject = res.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    topics = await db.execute(
        select(Topic.id).where(Topic.subject_id == scope_id, Topic.user_id == user_id)
    )
    return [r[0] for r in topics.all()], subject.name


async def _scope_chunks(db: AsyncSession, user_id: str, topic_ids: list[UUID]) -> list[dict]:
    if not topic_ids:
        return []
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


def _public(exam: ExamSession) -> ExamSessionPublic:
    questions = [
        ExamQuestionPublic(index=i, stem=q["stem"], options=q["options"])
        for i, q in enumerate(exam.questions_json)
    ]
    return ExamSessionPublic(
        id=exam.id,
        scope_type=exam.scope_type,
        scope_id=exam.scope_id,
        scope_name=exam.scope_name,
        num_questions=exam.num_questions,
        status=exam.status,
        questions=questions,
        created_at=exam.created_at,
    )


def _result(exam: ExamSession) -> ExamResult:
    answers = exam.answers_json or {}
    results: list[ExamQuestionResult] = []
    correct = 0
    for i, q in enumerate(exam.questions_json):
        selected = answers.get(str(i))
        is_correct = selected == q["correct_index"]
        if is_correct:
            correct += 1
        results.append(
            ExamQuestionResult(
                index=i,
                stem=q["stem"],
                options=q["options"],
                correct_index=q["correct_index"],
                selected_index=selected,
                is_correct=is_correct,
                explanation=q.get("explanation", ""),
                source=q.get("source"),
            )
        )
    total = len(exam.questions_json)
    return ExamResult(
        id=exam.id,
        status=exam.status,
        score=exam.score if exam.score is not None else (correct / total * 100 if total else 0),
        total=total,
        correct=correct,
        duration_seconds=exam.duration_seconds,
        questions=results,
    )


@router.post("", response_model=ExamSessionPublic)
async def create_exam(
    body: ExamCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExamSessionPublic:
    user_id = current_user["user_id"]
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    topic_ids, scope_name = await _scope(db, user_id, body.scope_type, body.scope_id)
    chunks = await _scope_chunks(db, user_id, topic_ids)
    if not chunks:
        raise HTTPException(status_code=409, detail="Sem material processado para gerar a prova.")

    try:
        questions = await generate_exam_from_chunks(chunks, body.num_questions)
    except Exception as exc:
        logger.exception("Exam generation failed", extra={"user_id": user_id})
        raise HTTPException(status_code=502, detail="Falha ao gerar a prova. Tente novamente.") from exc

    exam = ExamSession(
        user_id=user_id,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        scope_name=scope_name,
        num_questions=len(questions),
        status="in_progress",
        questions_json=questions,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return _public(exam)


async def _get_exam(exam_id: UUID, user_id: str, db: AsyncSession) -> ExamSession:
    res = await db.execute(
        select(ExamSession).where(ExamSession.id == exam_id, ExamSession.user_id == user_id)
    )
    exam = res.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


@router.get("/{exam_id}", response_model=ExamSessionPublic)
async def get_exam(
    exam_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExamSessionPublic:
    exam = await _get_exam(exam_id, current_user["user_id"], db)
    return _public(exam)


@router.post("/{exam_id}/finish", response_model=ExamResult)
async def finish_exam(
    exam_id: UUID,
    body: ExamAnswers,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExamResult:
    exam = await _get_exam(exam_id, current_user["user_id"], db)
    total = len(exam.questions_json)
    correct = sum(
        1 for i, q in enumerate(exam.questions_json) if body.answers.get(str(i)) == q["correct_index"]
    )
    exam.answers_json = body.answers
    exam.score = (correct / total * 100) if total else 0
    exam.duration_seconds = body.duration_seconds
    exam.status = "finished"
    exam.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(exam)
    return _result(exam)
