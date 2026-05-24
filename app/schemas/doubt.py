from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


DoubtStatus = Literal["pending", "resolved", "converted_to_flashcard"]


class DoubtCreate(BaseModel):
    topic_id: UUID
    question: str
    material_id: UUID | None = None
    ai_answer: str | None = None

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be empty")
        return value


class DoubtResolveRequest(BaseModel):
    create_flashcard: bool = False


class DoubtResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic_id: UUID
    material_id: UUID | None = None
    question: str
    ai_answer: str | None = None
    status: DoubtStatus
    resolved_at: datetime | None = None
    flashcard_id: UUID | None = None
    created_at: datetime
    subject_name: str | None = None
    topic_name: str | None = None

    model_config = {"from_attributes": True}


class SubjectPendingSummary(BaseModel):
    subject_id: UUID
    subject_name: str
    pending_count: int


class DoubtSummaryResponse(BaseModel):
    pending_total: int
    pending_by_subject: list[SubjectPendingSummary]
