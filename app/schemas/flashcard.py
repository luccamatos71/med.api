from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

FlashcardSource = Literal["ai_generated", "manual", "from_doubt"]


class FlashcardGenerateResponse(BaseModel):
    queued: bool


class FlashcardCreate(BaseModel):
    topic_id: UUID
    material_id: UUID | None = None
    front: str
    back: str

    @field_validator("front", "back")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("front/back cannot be empty")
        return text


class FlashcardUpdate(BaseModel):
    front: str | None = None
    back: str | None = None
    topic_id: UUID | None = None
    material_id: UUID | None = None
    source_snippet: str | None = None
    page_number: int | None = None
    approve_now: bool = False

    @field_validator("front", "back", "source_snippet")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("text fields cannot be empty")
        return text


class FlashcardResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic_id: UUID
    material_id: UUID | None
    doubt_id: UUID | None
    source: FlashcardSource
    front: str
    back: str
    source_snippet: str | None
    page_number: int | None
    ai_approved_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    subject_id: UUID | None = None
    topic_name: str | None = None
    subject_name: str | None = None
    material_title: str | None = None

    model_config = {"from_attributes": True}
