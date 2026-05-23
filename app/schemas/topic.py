from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class TopicCreate(BaseModel):
    subject_id: UUID
    name: str
    parent_topic_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class TopicUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class TopicResponse(BaseModel):
    id: UUID
    subject_id: UUID
    parent_topic_id: Optional[UUID]
    name: str
    position: int
    created_at: datetime
    subtopics: List["TopicResponse"] = []

    model_config = {"from_attributes": True}


TopicResponse.model_rebuild()


class ReorderItem(BaseModel):
    id: UUID
    position: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]
