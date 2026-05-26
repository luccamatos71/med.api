from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

RatingType = Literal["again", "hard", "good", "easy"]
ReviewState = Literal["new", "learning", "review", "relearning"]


class ReviewIntervalPreview(BaseModel):
    rating: RatingType
    label: str
    interval: str


class ReviewCardResponse(BaseModel):
    flashcard_id: UUID
    topic_id: UUID
    subject_id: UUID | None = None
    front: str
    back: str
    source_snippet: str | None
    page_number: int | None
    source: str
    due_date: datetime
    state: ReviewState
    reps: int
    lapses: int
    intervals: list[ReviewIntervalPreview]


class ReviewSessionResponse(BaseModel):
    cards: list[ReviewCardResponse]
    new_count: int
    review_count: int
    total: int


class ReviewRateRequest(BaseModel):
    flashcard_id: UUID
    rating: RatingType


class ReviewRateResponse(BaseModel):
    flashcard_id: UUID
    rating: RatingType
    state: ReviewState
    stability: float | None
    difficulty: float | None
    elapsed_days: int
    scheduled_days: int
    reps: int
    lapses: int
    due_date: datetime
    intervals: list[ReviewIntervalPreview]
