import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


ALLOWED_COLORS = {
    "#2EA39E", "#D97706", "#2E7D52", "#9B2226",
    "#3B82F6", "#8B5CF6", "#EC4899", "#F59E0B",
}


class SubjectCreate(BaseModel):
    name: str
    color: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v

    @field_validator("color")
    @classmethod
    def color_valid(cls, v: str) -> str:
        if v not in ALLOWED_COLORS:
            raise ValueError(f"color must be one of {ALLOWED_COLORS}")
        return v


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name cannot be empty")
        return v

    @field_validator("color")
    @classmethod
    def color_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_COLORS:
            raise ValueError(f"color must be one of {ALLOWED_COLORS}")
        return v


class SubjectResponse(BaseModel):
    id: UUID
    name: str
    color: str
    archived: bool
    created_at: datetime
    topic_count: int = 0

    model_config = {"from_attributes": True}


class ChildrenCount(BaseModel):
    topics: int
    materials: int = 0
    flashcards: int = 0
