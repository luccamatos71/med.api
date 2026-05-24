from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str
    selected_text: str | None = None


class CitedChunk(BaseModel):
    chunk_id: str
    material_title: str
    page_number: int | None = None
    snippet: str


class ChatMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    cited_chunks: list[CitedChunk] = Field(default_factory=list)
    tokens_used: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
