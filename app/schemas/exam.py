from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    scope_type: Literal["subject", "topic"]
    scope_id: UUID
    num_questions: int = Field(default=10, ge=3, le=30)


class ExamQuestionPublic(BaseModel):
    """Question as shown during the exam (no answer key)."""

    index: int
    stem: str
    options: list[str]


class ExamSessionPublic(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    scope_name: str | None
    num_questions: int
    status: str
    questions: list[ExamQuestionPublic]
    created_at: datetime


class ExamAnswers(BaseModel):
    # question index (as string) -> chosen option index
    answers: dict[str, int]
    duration_seconds: int | None = None


class ExamQuestionResult(BaseModel):
    index: int
    stem: str
    options: list[str]
    correct_index: int
    selected_index: int | None
    is_correct: bool
    explanation: str
    source: dict | None = None


class ExamResult(BaseModel):
    id: UUID
    status: str
    score: float
    total: int
    correct: int
    duration_seconds: int | None
    questions: list[ExamQuestionResult]


class ExamHistoryItem(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    scope_name: str | None
    num_questions: int
    status: str
    score: float | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ExamHistory(BaseModel):
    average_score: float | None
    total_exams: int
    items: list[ExamHistoryItem]


class WrongToFlashcardsResult(BaseModel):
    created: int
