from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.chat import CitedChunk


class ConversationCreate(BaseModel):
    title: str | None = None
    topic_id: UUID | None = None
    material_id: UUID | None = None


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None = None
    topic_id: UUID | None = None
    material_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssistantMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    cited_chunks: list[CitedChunk] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class AssistantChatRequest(BaseModel):
    question: str
    # Optional context — set when asking from inside a material viewer.
    active_material_id: UUID | None = None
    selected_text: str | None = None
