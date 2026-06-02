from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StudyPlanCreate(BaseModel):
    exam_date: date
    subject_ids: list[UUID] = Field(default_factory=list)


class StudyTask(BaseModel):
    type: str  # study | review | exam
    label: str
    topic_id: UUID | None = None
    subject_id: UUID | None = None


class StudyDay(BaseModel):
    date: date
    tasks: list[StudyTask] = Field(default_factory=list)


class StudyPlanResponse(BaseModel):
    id: UUID
    exam_date: date
    status: str
    overview: str
    summary: dict
    days: list[StudyDay]
    created_at: datetime
