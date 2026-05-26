from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.flashcard import Flashcard
from app.models.flashcard_review import FlashcardReview
from app.models.review_log import ReviewLog
from app.models.subject import Subject
from app.models.topic import Topic
from app.schemas.review import (
    ReviewCardResponse,
    ReviewRateRequest,
    ReviewRateResponse,
    ReviewSessionResponse,
)
from app.services.fsrs_service import apply_rating, preview_intervals

router = APIRouter(prefix="/review", tags=["review"])


def _session_row_to_card(row, intervals: list[dict[str, str]]) -> ReviewCardResponse:
    return ReviewCardResponse(
        flashcard_id=row.flashcard_id,
        topic_id=row.topic_id,
        subject_id=row.subject_id,
        front=row.front,
        back=row.back,
        source_snippet=row.source_snippet,
        page_number=row.page_number,
        source=row.source,
        due_date=row.due_date,
        state=row.state,
        reps=row.reps,
        lapses=row.lapses,
        intervals=intervals,
    )


@router.get("/session", response_model=ReviewSessionResponse)
async def get_review_session(
    filter: str = Query(default="due"),
    subject_id: UUID | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewSessionResponse:
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    filters = [
        Flashcard.user_id == user_id,
        Flashcard.archived_at.is_(None),
        Flashcard.ai_approved_at.is_not(None),
    ]
    if subject_id:
        filters.append(Subject.id == subject_id)
    if filter == "due":
        filters.append(FlashcardReview.due_date <= now)

    stmt = (
        select(
            Flashcard.id.label("flashcard_id"),
            Flashcard.topic_id.label("topic_id"),
            Subject.id.label("subject_id"),
            Flashcard.front.label("front"),
            Flashcard.back.label("back"),
            Flashcard.source_snippet.label("source_snippet"),
            Flashcard.page_number.label("page_number"),
            Flashcard.source.label("source"),
            FlashcardReview.due_date.label("due_date"),
            FlashcardReview.state.label("state"),
            FlashcardReview.reps.label("reps"),
            FlashcardReview.lapses.label("lapses"),
        )
        .join(FlashcardReview, FlashcardReview.flashcard_id == Flashcard.id)
        .join(Topic, Topic.id == Flashcard.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .where(and_(*filters))
        .order_by(FlashcardReview.due_date.asc(), Flashcard.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    cards: list[ReviewCardResponse] = []
    new_count = 0
    review_count = 0
    for row in rows:
        review_stmt = await db.execute(
            select(FlashcardReview).where(FlashcardReview.flashcard_id == row.flashcard_id)
        )
        review = review_stmt.scalar_one()
        intervals = preview_intervals(review, now=now)
        cards.append(_session_row_to_card(row, intervals))
        if row.state == "new":
            new_count += 1
        if row.state in ("review", "relearning"):
            review_count += 1

    return ReviewSessionResponse(
        cards=cards,
        new_count=new_count,
        review_count=review_count,
        total=len(cards),
    )


@router.post("/rate", response_model=ReviewRateResponse)
async def rate_flashcard(
    body: ReviewRateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewRateResponse:
    user_id = current_user["user_id"]
    card_stmt = await db.execute(
        select(Flashcard).where(
            Flashcard.id == body.flashcard_id,
            Flashcard.user_id == user_id,
            Flashcard.archived_at.is_(None),
            Flashcard.ai_approved_at.is_not(None),
        )
    )
    flashcard = card_stmt.scalar_one_or_none()
    if not flashcard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")

    review_stmt = await db.execute(
        select(FlashcardReview).where(
            FlashcardReview.flashcard_id == body.flashcard_id,
            FlashcardReview.user_id == user_id,
        )
    )
    review = review_stmt.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review state not found")

    stability_before = review.stability
    apply_rating(review, body.rating)
    db.add(
        ReviewLog(
            flashcard_id=body.flashcard_id,
            user_id=user_id,
            rating=body.rating,
            review_time=datetime.now(timezone.utc),
            stability_before=stability_before,
            stability_after=review.stability,
        )
    )
    await db.commit()
    await db.refresh(review)

    return ReviewRateResponse(
        flashcard_id=body.flashcard_id,
        rating=body.rating,
        state=review.state,
        stability=review.stability,
        difficulty=review.difficulty,
        elapsed_days=review.elapsed_days,
        scheduled_days=review.scheduled_days,
        reps=review.reps,
        lapses=review.lapses,
        due_date=review.due_date,
        intervals=preview_intervals(review),
    )
